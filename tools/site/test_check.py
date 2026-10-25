import json
import shutil
import tempfile
import unittest
from pathlib import Path
import check


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.site=Path(self.tmp.name)/'site';shutil.copytree(check.ROOT/'site',self.site)

    def edit(self,path,old,new):
        file=self.site/path;text=file.read_text();self.assertIn(old,text);file.write_text(text.replace(old,new))

    def policy(self,update):
        path=self.site/'release.json';value=json.loads(path.read_text());update(value);path.write_text(json.dumps(value))

    def health(self,**changes):
        return {'ok':True,'mode':'production','signups_enabled':False,'customer_limit':25,**changes}

    def test_reviewed_release_and_closed_backend_pass(self):
        r=check.validate(self.site);self.assertTrue(r['sample_preserved'])
        self.assertTrue(check.verify_backend(r,lambda:self.health())['backend_checked'])

    def test_wrong_price_is_blocked(self):
        self.edit('index.html','R$ 9,90','R$ 19,90')
        with self.assertRaisesRegex(check.InvalidRelease,'price'):check.validate(self.site)

    def test_monthly_recurrence_cannot_disappear(self):
        self.edit('index.html','por mês','por ano')
        with self.assertRaisesRegex(check.InvalidRelease,'recurrence'):check.validate(self.site)

    def test_signup_cta_cannot_be_published_while_coming_soon(self):
        self.edit('index.html','href="#exemplo"','href="https://assinar.minutocomjesus.com.br/cadastro"')
        with self.assertRaisesRegex(check.InvalidRelease,'premature_signup'):check.validate(self.site)

    def test_opening_needs_explicit_policy_and_the_public_backend_capacity(self):
        self.policy(lambda p:p.update(availability='open'))
        with self.assertRaisesRegex(check.InvalidRelease,'opening_not_authorized'):check.validate(self.site)
        self.policy(lambda p:p.update(opening_authorized=True))
        self.edit('index.html','As assinaturas estarão disponíveis em breve.','Assinaturas disponíveis.')
        self.edit('index.html','href="#exemplo"','href="https://assinar.minutocomjesus.com.br/cadastro"')
        r=check.validate(self.site)
        for h in [self.health(),self.health(signups_enabled=True),self.health(signups_enabled=True,customer_limit=1)]:
            with self.assertRaises(check.InvalidRelease):check.verify_backend(r,lambda:h)
        self.assertTrue(check.verify_backend(r,lambda:self.health(signups_enabled=True,customer_limit=1000))['backend_checked'])

    def test_hidden_single_participant_trial_is_compatible_with_coming_soon(self):
        r=check.validate(self.site)
        self.assertTrue(check.verify_backend(r,lambda:self.health(signups_enabled=True,customer_limit=1))['backend_checked'])
        with self.assertRaises(check.InvalidRelease):check.verify_backend(r,lambda:self.health(signups_enabled=True,customer_limit=1000))

    def test_malformed_backend_or_unknown_health_field_is_rejected(self):
        r=check.validate(self.site)
        for h in [None,self.health(ok=1),self.health(customer_limit=True),self.health(secret='private'),self.health(admissions_paused=False)]:
            with self.assertRaises(check.InvalidRelease):check.verify_backend(r,lambda:h)

    def test_sample_text_image_and_open_graph_remain_coherent(self):
        self.edit('index.html','og:image" content="https://minutocomjesus.com.br/assets/bom-dia-exemplo-tiago-4-8.jpg','og:image" content="https://minutocomjesus.com.br/assets/bom-dia-exemplo.jpg')
        with self.assertRaises(check.InvalidRelease):check.validate(self.site)
        shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
        self.edit('index.html','Tiago nos convida','Outro texto convida')
        with self.assertRaisesRegex(check.InvalidRelease,'sample_changed'):check.validate(self.site)
        shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
        (self.site/'assets/bom-dia-exemplo-tiago-4-8.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(check.InvalidRelease,'sample_changed'):check.validate(self.site)

    def test_contract_page_or_attachment_change_needs_a_reviewed_hash(self):
        self.edit('termos.html','R$ 9,90','R$ 10,90')
        with self.assertRaisesRegex(check.InvalidRelease,'document_hash'):check.validate(self.site)
        shutil.copyfile(check.ROOT/'site/termos.html',self.site/'termos.html')
        p=self.site/'contratos/commercial-2026-10-14-v4.txt';p.write_text(p.read_text()+'changed')
        with self.assertRaisesRegex(check.InvalidRelease,'document_hash'):check.validate(self.site)

    def test_missing_local_asset_and_broken_fragment_are_blocked(self):
        self.edit('index.html','./style.css?v=20261024','./absent.css')
        with self.assertRaisesRegex(check.InvalidRelease,'missing_or_unsafe_asset'):check.validate(self.site)
        shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
        self.edit('index.html','href="#exemplo"','href="#missing"')
        with self.assertRaisesRegex(check.InvalidRelease,'broken_fragment'):check.validate(self.site)

    def test_remote_tracking_resource_and_css_import_are_blocked(self):
        self.edit('index.html','./style.css?v=20261024','https://tracking.example/style.css')
        with self.assertRaises(check.InvalidRelease):check.validate(self.site)
        shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
        p=self.site/'style.css';p.write_text(p.read_text()+'\n@import "https://tracking.example/";')
        with self.assertRaisesRegex(check.InvalidRelease,'unreviewed_resource'):check.validate(self.site)

    def test_path_traversal_and_javascript_link_are_rejected(self):
        for value in ['../README.md','%2e%2e/README.md','javascript:alert(1)','//tracking.example/x']:
            shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
            self.edit('index.html','href="#exemplo"',f'href="{value}"')
            with self.assertRaises(check.InvalidRelease):check.validate(self.site)

    def test_placeholder_is_blocked_without_confusing_portuguese_todo_with_a_marker(self):
        self.assertEqual(check.validate(self.site)['status'],'verified')
        self.edit('index.html','As assinaturas estarão disponíveis em breve.','{{availability}}')
        with self.assertRaisesRegex(check.InvalidRelease,'unreviewed_page_content'):check.validate(self.site)

    def test_scripts_iframes_forms_and_event_handlers_require_review(self):
        for injected in ['<script src="x.js"></script>','<iframe src="https://tracking.example"></iframe>','<form></form>','<img src="x" alt="x" onerror="x()">']:
            shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
            self.edit('index.html','</body>',injected+'</body>')
            with self.assertRaises(check.InvalidRelease):check.validate(self.site)

    def test_duplicate_ids_and_image_without_alt_are_blocked(self):
        self.edit('index.html','id="inicio"','id="conteudo"')
        with self.assertRaisesRegex(check.InvalidRelease,'duplicate_html_id'):check.validate(self.site)
        shutil.copyfile(check.ROOT/'site/index.html',self.site/'index.html')
        self.edit('index.html','alt="Card','data-description="Card')
        with self.assertRaisesRegex(check.InvalidRelease,'image_alt_missing'):check.validate(self.site)

    def test_unreviewed_file_cannot_be_uploaded_with_the_site(self):
        (self.site/'database.sql').write_text('private')
        with self.assertRaisesRegex(check.InvalidRelease,'unreviewed_site_file'):check.validate(self.site)


if __name__=='__main__':unittest.main()
