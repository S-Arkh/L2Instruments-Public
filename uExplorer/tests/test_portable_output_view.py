"""Managed portable output must never replace unrelated directories."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/'tools/package_windows.py'
spec=importlib.util.spec_from_file_location('package_windows',path)
package=importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PortableOutput(unittest.TestCase):
    def test_existing_unmanaged_and_managed_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);unmanaged=root/'unmanaged';unmanaged.mkdir()
            (unmanaged/'keep').write_text('user work')
            with self.assertRaisesRegex(ValueError,'not a managed'):
                package.prepare_output(unmanaged)
            self.assertEqual((unmanaged/'keep').read_text(),'user work')
            managed=root/'portable';package.prepare_output(managed)
            (managed/'old-result').write_text('old')
            package.prepare_output(managed)
            self.assertFalse((managed/'old-result').exists())
            self.assertTrue((managed/'.uexplorer-package-output').is_file())

    def test_link_and_dangling_link_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);managed=root/'managed';package.prepare_output(managed)
            (managed/'keep').write_text('still here')
            for target in (managed,root/'absent'):
                link=root/('link-'+target.name)
                try:link.symlink_to(target,target_is_directory=True)
                except OSError:self.skipTest('Directory symlink creation is unavailable')
                with self.assertRaisesRegex(ValueError,'symbolic link'):
                    package.prepare_output(link)
            self.assertEqual((managed/'keep').read_text(),'still here')


if __name__=='__main__':unittest.main()
