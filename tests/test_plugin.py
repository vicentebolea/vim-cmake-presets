import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures')


def vim_eval(commands, expr, cwd=FIXTURE, pre=()):
    """Run commands in headless Vim after opening the sidebar; return expr."""
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
        out = os.path.join(d, 'out')
        args = ['vim', '-es', '-u', 'NONE', '-N', '--cmd', 'syntax on']
        for c in pre:
            args += ['--cmd', c]
        args += ['--cmd', 'set rtp+=' + ROOT,
                 '-c', 'runtime plugin/cmake_presets.vim', '-c', 'CMakePresets']
        for c in commands:
            args += ['-c', c]
        args += ['-c', 'call writefile([json_encode(%s)], "%s")' % (expr, out),
                 '-c', 'qa!']
        subprocess.run(args, cwd=cwd, check=True, timeout=30)
        with open(out) as f:
            return json.load(f)


def term_cmd(search, key):
    # The terminal job really runs, so keep it away from the fixtures.
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
        shutil.copytree(FIXTURE, d, dirs_exist_ok=True)
        return vim_eval(['call search("%s")' % search, 'normal ' + key],
                        'job_info(term_getjob(bufnr("%")))["cmd"]', cwd=d)


class SidebarTest(unittest.TestCase):
    def test_sections_and_default(self):
        lines = vim_eval([], 'getline(1, "$")')
        self.assertIn('Configure', lines)
        self.assertIn('Build', lines)
        self.assertEqual(lines.count('+ default (default) [CMakePresets]'), 2)
        self.assertLess(lines.index('Configure'), lines.index('Build'))

    def test_source_file_shown(self):
        lines = vim_eval([], 'getline(1, "$")')
        self.assertIn('+ mine [CMakeUserPresets]', lines)
        self.assertIn('+ debug [CMakePresets]', lines)

    def test_source_file_commented_color(self):
        out = vim_eval(['call search("mine")'],
                       'synIDattr(synID(line("."), col("$") - 2, 1), "name")')
        self.assertEqual(out, 'CMakePresetsSource')

    def test_hidden_preset_omitted(self):
        self.assertNotIn('+ base', vim_eval([], 'getline(1, "$")'))

    def test_default_highlighted_red(self):
        out = vim_eval(['call search("(default)")'],
                       'synIDattr(synID(line("."), 5, 1), "name")')
        self.assertEqual(out, 'CMakePresetsDefault')

    def test_help_one_option_per_line_at_bottom(self):
        lines = vim_eval(['normal G'], 'getline(1, "$")')
        self.assertEqual(lines[-1], 'q     close')
        self.assertIn('o     open preset in file', lines)
        self.assertIn('B     build', lines[-7:])
        self.assertIn('C     configure', lines[-7:])

    def test_sidebar_on_right(self):
        name = vim_eval(['wincmd t', 'wincmd l'], 'bufname("%")')
        self.assertEqual(name, '[CMake Presets]')

    def test_toggle_closes(self):
        self.assertEqual(vim_eval(['CMakePresets'], 'winnr("$")'), 1)

    def test_no_presets_file(self):
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
            lines = vim_eval([], 'getline(1, "$")', cwd=d)
        self.assertIn('No CMakePresets.json found', lines)


class ActionTest(unittest.TestCase):
    def test_configure(self):
        self.assertEqual(term_cmd('^+ debug', 'C'), ['cmake', '--preset', 'debug'])

    def test_build_uses_build_preset(self):
        self.assertEqual(term_cmd('^+ debug', 'B'),
                         ['cmake', '--build', '--preset', 'build-debug'])

    def test_build_falls_back_to_binary_dir(self):
        cmd = term_cmd('^+ release', 'B')
        self.assertEqual(cmd[:2], ['cmake', '--build'])
        self.assertTrue(cmd[2].endswith(os.path.join('build', 'release')))

    def test_build_section_entry(self):
        self.assertEqual(term_cmd('build-debug', 'B'),
                         ['cmake', '--build', '--preset', 'build-debug'])

    def test_configure_from_build_entry(self):
        self.assertEqual(term_cmd('build-debug', 'C'),
                         ['cmake', '--preset', 'debug'])


class EditTest(unittest.TestCase):
    def test_o_opens_file_at_preset(self):
        out = vim_eval(['call search("^+ release")', 'normal o'],
                       '[expand("%:t"), getline(".")]')
        self.assertEqual(out[0], 'CMakePresets.json')
        self.assertIn('"release"', out[1])


    def test_enter_expands_and_collapses(self):
        enter = 'execute "normal \\<CR>"'
        found = ['call search("^+ release")']
        lines = vim_eval(found + [enter], 'getline(1, "$")')
        self.assertIn('- release [CMakePresets]', lines)
        self.assertIn('    inherits: base', lines)
        lines = vim_eval(found + [enter, 'call search("^- release")', enter],
                         'getline(1, "$")')
        self.assertIn('+ release [CMakePresets]', lines)
        self.assertNotIn('    inherits: base', lines)

    def test_flags_and_variables_colored(self):
        enter = 'execute "normal \\<CR>"'
        syn = 'synIDattr(synID(line("."), %d, 1), "name")'
        expand = ['call search("^+ release")', enter]
        self.assertEqual(vim_eval(expand + ['call search("generator")'], syn % 5),
                         'CMakePresetsFlag')
        self.assertEqual(vim_eval(expand + ['call search("CMAKE_BUILD_TYPE")'], syn % 8),
                         'CMakePresetsVar')

    def test_o_on_default_configure_opens_configure_preset(self):
        out = vim_eval(['call search("^+ default")', 'normal o'], 'getline(".")')
        self.assertIn('"inherits": "base"', out)

    def test_o_on_default_build_opens_build_preset(self):
        out = vim_eval(['call search("^Build")', 'call search("^+ default")',
                        'normal o'], 'getline(".")')
        self.assertIn('"configurePreset": "default"', out)

    def test_click_mapped_to_expand(self):
        out = vim_eval([], 'maparg("<LeftMouse>", "n", 0, 1)')
        self.assertEqual(out['buffer'], 1)
        self.assertIn('expand()', out['rhs'])

    def test_expand_shows_build_flags(self):
        lines = vim_eval(['call search("^+ build-debug")', 'execute "normal \\<CR>"'],
                         'getline(1, "$")')
        self.assertIn('    configurePreset: debug', lines)


class MappingTest(unittest.TestCase):
    def mapping(self, key, pre=()):
        return vim_eval([], 'maparg("%s", "n")' % key, pre=pre)

    def test_default_f8(self):
        self.assertEqual(self.mapping('<F8>'), ':CMakePresets<CR>')

    def test_custom_key(self):
        pre = ['let g:cmake_presets_map = "<F9>"']
        self.assertEqual(self.mapping('<F9>', pre), ':CMakePresets<CR>')
        self.assertEqual(self.mapping('<F8>', pre), '')

    def test_empty_disables(self):
        self.assertEqual(self.mapping('<F8>', ['let g:cmake_presets_map = ""']), '')


class OpenCacheTest(unittest.TestCase):
    def open_cache(self, search, configured=True):
        os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
            shutil.copytree(FIXTURE, d, dirs_exist_ok=True)
            if configured:
                os.makedirs(os.path.join(d, 'build', 'debug'))
                open(os.path.join(d, 'build', 'debug', 'CMakeCache.txt'), 'w').close()
            return vim_eval(['call search("%s")' % search, 'normal v'],
                            'expand("%:t")', cwd=d)

    def test_v_opens_cache(self):
        self.assertEqual(self.open_cache('^+ debug'), 'CMakeCache.txt')

    def test_v_on_build_entry_opens_cache(self):
        self.assertEqual(self.open_cache('^+ build-debug'), 'CMakeCache.txt')

    def test_v_unconfigured_stays_in_sidebar(self):
        self.assertEqual(self.open_cache('^+ debug', False), '[CMake Presets]')


class CleanTest(unittest.TestCase):
    def run_clean(self, answer, key_search='^+ debug'):
        os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
            shutil.copytree(FIXTURE, d, dirs_exist_ok=True)
            os.makedirs(os.path.join(d, 'build', 'debug'))
            open(os.path.join(d, 'build', 'debug', 'CMakeCache.txt'), 'w').close()
            vim_eval(['py3 cmake_presets.ask = lambda p: %s' % answer,
                      'call search("%s")' % key_search, 'normal X'], '1', cwd=d)
            return os.path.isdir(os.path.join(d, 'build', 'debug'))

    def test_yes_deletes_build_dir(self):
        self.assertFalse(self.run_clean('True'))

    def test_no_keeps_build_dir(self):
        self.assertTrue(self.run_clean('False'))

    def test_unconfigured_preset_is_noop(self):
        self.assertTrue(self.run_clean('True', '^+ release'))


def cmake_at_least(major, minor):
    try:
        out = subprocess.run(['cmake', '--version'], capture_output=True,
                             text=True).stdout.split()[2]
    except (OSError, IndexError):
        return False
    return tuple(int(x) for x in out.split('.')[:2]) >= (major, minor)


@unittest.skipUnless(cmake_at_least(3, 21) and shutil.which('cc'),
                     'needs cmake >= 3.21 and a C compiler')
class CProjectTest(unittest.TestCase):
    def test_configure_and_build_c_project(self):
        os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
        configure = term_cmd('^+ debug', 'C')
        build = term_cmd('^+ debug', 'B')
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
            shutil.copytree(FIXTURE, d, dirs_exist_ok=True)
            for cmd in (configure, build):
                subprocess.run(cmd, cwd=d, check=True, capture_output=True)
            exe = os.path.join(d, 'build', 'debug', 'hello')
            out = subprocess.run([exe], capture_output=True, text=True).stdout
            self.assertIn('hello from vim-cmake-presets', out)


if __name__ == '__main__':
    unittest.main()
