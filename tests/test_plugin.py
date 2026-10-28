import json
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures')


def vim_eval(commands, expr, cwd=FIXTURE):
    """Run commands in headless Vim after opening the sidebar; return expr."""
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'tmp')) as d:
        out = os.path.join(d, 'out')
        args = ['vim', '-es', '-u', 'NONE', '-N', '--cmd', 'syntax on', '--cmd', 'set rtp+=' + ROOT,
                '-c', 'runtime plugin/cmake_presets.vim', '-c', 'CMakePresets']
        for c in commands:
            args += ['-c', c]
        args += ['-c', 'call writefile([json_encode(%s)], "%s")' % (expr, out),
                 '-c', 'qa!']
        subprocess.run(args, cwd=cwd, check=True, timeout=30)
        with open(out) as f:
            return json.load(f)


def term_cmd(search, key):
    return vim_eval(['call search("%s")' % search, 'normal ' + key],
                    'job_info(term_getjob(bufnr("%")))["cmd"]')


class SidebarTest(unittest.TestCase):
    def test_sections_and_default(self):
        lines = vim_eval([], 'getline(1, "$")')
        self.assertIn('Configure', lines)
        self.assertIn('Build', lines)
        self.assertEqual(lines.count('+ default (default)'), 2)
        self.assertLess(lines.index('Configure'), lines.index('Build'))

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
        self.assertIn('B     build', lines[-4:])
        self.assertIn('C     configure', lines[-4:])

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
        self.assertEqual(cmd, ['cmake', '--build',
                               os.path.join(FIXTURE, 'build/release')])

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
        self.assertIn('- release', lines)
        self.assertIn('    inherits: base', lines)
        lines = vim_eval(found + [enter, 'call search("^- release")', enter],
                         'getline(1, "$")')
        self.assertIn('+ release', lines)
        self.assertNotIn('    inherits: base', lines)

    def test_flags_and_variables_colored(self):
        enter = 'execute "normal \\<CR>"'
        syn = 'synIDattr(synID(line("."), %d, 1), "name")'
        expand = ['call search("^+ release")', enter]
        self.assertEqual(vim_eval(expand + ['call search("generator")'], syn % 5),
                         'CMakePresetsFlag')
        self.assertEqual(vim_eval(expand + ['call search("CMAKE_BUILD_TYPE")'], syn % 8),
                         'CMakePresetsVar')

    def test_click_mapped_to_expand(self):
        out = vim_eval([], 'maparg("<LeftMouse>", "n", 0, 1)')
        self.assertEqual(out['buffer'], 1)
        self.assertIn('expand()', out['rhs'])

    def test_expand_shows_build_flags(self):
        lines = vim_eval(['call search("^+ build-debug")', 'execute "normal \\<CR>"'],
                         'getline(1, "$")')
        self.assertIn('    configurePreset: debug', lines)


if __name__ == '__main__':
    unittest.main()
