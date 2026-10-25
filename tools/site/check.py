"""Validate the reviewed static release before packaging. Standard library only."""
import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = 'https://minutocomjesus.com.br'
BACKEND = 'https://assinar.minutocomjesus.com.br'
PLACEHOLDERS = re.compile(r'\{\{[^{}]{0,200}\}\}|\b(?:TODO|PLACEHOLDER|SEUSUBDOMINIO|SEU_CPF|SEU_NOME|SEU_ENDERECO)\b')
EXTERNAL_LINK_HOSTS = {'github.com','creativecommons.org','resend.com','www.cloudflare.com','workspace.google.com','docs.github.com','www.mercadopago.com.br','assinar.minutocomjesus.com.br'}
sha256 = lambda data: hashlib.sha256(data).hexdigest()


class InvalidRelease(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise InvalidRelease(code)


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.resources, self.text, self.meta, self.styles = set(), [], [], [], {}, []
        self.lang = None
        self.blocked = False
        self.in_style = False
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        a = dict(attributes)
        require(len(a)==len(attributes), 'duplicate_html_attribute')
        if 'id' in a:
            require(a['id'] not in self.ids, 'duplicate_html_id')
            self.ids.add(a['id'])
        if tag=='html': self.lang=a.get('lang')
        if tag=='style':self.in_style=True
        if tag in ('script','iframe','object','embed','form','base','video','audio','source','track','picture','svg','math') or any(k.startswith('on') for k in a): self.blocked=True
        if any(k in a for k in ('http-equiv','background','srcdoc','ping','poster','formaction')) or tag!='img' and 'src' in a:self.blocked=True
        if tag=='a': self.links.append(a.get('href',''))
        if tag=='link':
            require(a.get('rel')=='stylesheet', 'unreviewed_resource')
            self.resources.append(a.get('href',''))
        if tag=='img':
            require(bool(a.get('alt','').strip()), 'image_alt_missing')
            self.resources.append(a.get('src',''))
        require('srcset' not in a and 'style' not in a, 'unreviewed_resource')
        if tag=='meta': self.meta[a.get('property') or a.get('name')]=a.get('content')

    def handle_data(self, text):
        if self.in_style:self.styles.append(text)
        else:self.text.append(text)

    def handle_endtag(self, tag):
        if tag=='style':self.in_style=False


def local_target(site, page_path, value, *, resource=False):
    require(isinstance(value,str) and value and not re.search(r'[\x00-\x20\\]', value), 'invalid_link')
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme=='mailto':
            require(not resource and value=='mailto:contato@minutocomjesus.com.br', 'unreviewed_contact')
            return None
        require(parsed.scheme=='https' and not parsed.username and not parsed.password and parsed.port in (None,443), 'unsafe_link')
        if parsed.netloc!='minutocomjesus.com.br':
            require(not resource and parsed.hostname in EXTERNAL_LINK_HOSTS, 'unreviewed_external_link')
            return None
        path=parsed.path.lstrip('/') or 'index.html'
    else:
        path=unquote(parsed.path)
        require(not urlsplit(path).scheme and not path.startswith('//'), 'unsafe_link')
        path=str(Path(page_path).parent/path) if path else str(page_path)
        if path.startswith('/'):path=path.lstrip('/')
    target=(site/path).resolve()
    require(target.is_relative_to(site.resolve()) and target.is_file() and not target.is_symlink(), 'missing_or_unsafe_asset')
    if parsed.fragment and target.suffix=='.html':
        require(unquote(parsed.fragment) in Page(target.read_text()).ids, 'broken_fragment')
    return target


def sample_markup(home):
    sample=re.search(r'<article\b[^>]*class="sample-card"[^>]*>(.*?)</article>', home, re.S)
    require(sample is not None, 'sample_missing')
    return sample[1]


def validate(site):
    site=Path(site)
    policy=json.loads((site/'release.json').read_text())
    require(set(policy)=={'schema_version','availability','opening_authorized','price_cents','currency','recurrence','backend_origin','public_customer_limit','documents','sample','inventory'}, 'release_policy_fields')
    require(type(policy['schema_version']) is int and policy['schema_version']==1 and policy['availability'] in ('coming_soon','open')
        and type(policy['opening_authorized']) is bool and policy['opening_authorized']==(policy['availability']=='open'), 'opening_not_authorized')
    require(type(policy['price_cents']) is int and policy['price_cents']==990 and policy['currency']=='BRL' and policy['recurrence']=='monthly'
        and policy['backend_origin']==BACKEND and type(policy['public_customer_limit']) is int and 25<policy['public_customer_limit']<=10000, 'commercial_offer_mismatch')
    actual=sorted(str(p.relative_to(site)) for p in site.rglob('*') if p.is_file() and p!=site/'release.json')
    require(actual==policy['inventory'] and all(not p.startswith('.') and '/.' not in p for p in actual), 'unreviewed_site_file')
    docs=policy['documents']
    require(isinstance(docs,dict) and set(docs)=={'version','sha256'} and re.fullmatch(r'commercial-\d{4}-\d{2}-\d{2}-v[1-9]\d*',docs['version']), 'document_version_invalid')
    require(set(docs['sha256'])=={'termos.html','privacidade.html','contratos/'+docs['version']+'.txt'}, 'document_set_invalid')
    for path,expected in docs['sha256'].items():
        require(re.fullmatch(r'[a-f0-9]{64}',expected) and sha256((site/path).read_bytes())==expected, 'document_hash_mismatch')
        require(docs['version'] in (site/path).read_text(), 'document_version_mismatch')
    pages={path.name:Page(path.read_text()) for path in sorted(site.glob('*.html'))}
    require(set(pages)=={'index.html','termos.html','privacidade.html'}, 'unreviewed_page')
    for name,page in pages.items():
        source=(site/name).read_text()
        require(page.lang=='pt-BR' and not page.blocked and not PLACEHOLDERS.search(source), 'unreviewed_page_content')
        for value in page.links:local_target(site,name,value)
        for value in page.resources:local_target(site,name,value,resource=True)
        require(not re.search(r'@import|image-set\(|https?:|//|\\', ''.join(page.styles),re.I), 'unreviewed_resource')
        for url in re.findall(r'url\(\s*[\'"]?([^\s\)\'";]+)',source):local_target(site,name,url,resource=True)
        for price in re.findall(r'R\$\s*([0-9]+(?:[.,][0-9]{2})?)',' '.join(page.text)):
            require(price.replace('.',',')=='9,90', 'displayed_price_mismatch')
    home=(site/'index.html').read_text()
    text=' '.join(pages['index.html'].text)
    require(re.search(r'R\$\s*9,90\s+por mês',text) and 'e-mail' in text and 'por mês' in ' '.join(pages['termos.html'].text), 'recurrence_or_channel_missing')
    signup=[url for page in pages.values() for url in page.links if urlsplit(url).hostname=='assinar.minutocomjesus.com.br']
    if policy['availability']=='coming_soon':
        require('As assinaturas estarão disponíveis em breve.' in text and not signup, 'premature_signup_link')
    else:
        require('estarão disponíveis em breve' not in text and BACKEND+'/cadastro' in pages['index.html'].links, 'opening_cta_missing')
    require(all(url==BACKEND+'/cadastro' for url in signup), 'unreviewed_backend_link')
    sample=policy['sample']
    require(set(sample)=={'image_path','image_sha256','markup_sha256','reference'}, 'sample_policy_invalid')
    require(sample['image_path']=='assets/bom-dia-exemplo-tiago-4-8.jpg' and sample['reference']=='Tiago 4:8', 'sample_reference_mismatch')
    require(sha256((site/sample['image_path']).read_bytes())==sample['image_sha256'] and sha256(sample_markup(home).encode())==sample['markup_sha256'], 'sample_changed_without_review')
    require(pages['index.html'].meta.get('og:image')==ORIGIN+'/'+sample['image_path'] and sample['reference'] in text
        and home.count('./'+sample['image_path'])==2 and 'Bíblia Livre (BLIVRE)' in text and 'CC BY 3.0 Brasil' in text, 'sample_links_or_credit_mismatch')
    for path in sorted(site.rglob('*')):
        require(not path.is_symlink(), 'symlink_in_site')
        if path.suffix=='.css':
            require(not re.search(r'@import|image-set\(|https?:|//|\\',path.read_text(),re.I), 'unreviewed_resource')
            for url in re.findall(r'url\(\s*[\'"]?([^\s\)\'";]+)',path.read_text()):local_target(site,path.relative_to(site),url,resource=True)
        require(path.suffix not in ('.js','.map','.sql','.env'), 'unreviewed_asset')
    return {'status':'verified','scope':'static_public_release','availability':policy['availability'],'price_cents':990,
        'document_version':docs['version'],'public_customer_limit':policy['public_customer_limit'],'html_pages':len(pages),'sample_preserved':True,'backend_checked':False,'production_opened':False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def verify_backend(report, read=None):
    if read is None:
        def read():
            req=Request(BACKEND+'/health',headers={'User-Agent':'MinutoComJesus/1.0','Accept':'application/json'})
            with build_opener(NoRedirect()).open(req,timeout=15) as response:
                require(response.status==200,'backend_unavailable')
                raw=response.read(8193);require(len(raw)<=8192,'backend_response_invalid')
                return json.loads(raw)
    health=read()
    require(isinstance(health,dict) and health.get('ok') is True and health.get('mode')=='production'
        and type(health.get('signups_enabled')) is bool and type(health.get('customer_limit')) is int
        and 1<=health['customer_limit']<=10000 and set(health).issubset({'ok','mode','signups_enabled','customer_limit','admissions_paused'}), 'backend_health_invalid')
    require('admissions_paused' not in health or health['admissions_paused'] is True and health['signups_enabled'] is False, 'backend_health_invalid')
    # A hidden one-person trial is compatible with a public coming-soon page.
    compatible=health['signups_enabled'] and health['customer_limit']==report['public_customer_limit']
    if report['availability']=='coming_soon':compatible=not health['signups_enabled'] or health['customer_limit']==1
    require(compatible,'site_backend_availability_mismatch')
    return {**report,'backend_checked':True,'backend_health':health}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',type=Path,default=ROOT/'site')
    parser.add_argument('--check-backend',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        report=validate(args.site)
        if args.check_backend:report=verify_backend(report)
    except (OSError,ValueError,TypeError,KeyError,OverflowError,AttributeError) as error:
        code=str(error) if isinstance(error,InvalidRelease) else 'site_release_validation_failed'
        report={'status':'blocked','scope':'static_public_release','reason':code,'production_opened':False}
    value=json.dumps(report,sort_keys=True)
    if args.output:args.output.write_text(value+'\n')
    print('PUBLIC_SITE_VALIDATION '+value)
    return 0 if report['status']=='verified' else 1


if __name__=='__main__':raise SystemExit(main())
