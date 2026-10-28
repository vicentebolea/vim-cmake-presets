import json
import os
import shutil

import vim

TITLE = 'CMake Presets'
HELP = [
    '<CR>  expand/collapse (or click)',
    'o     open preset in file',
    'B     build',
    'C     configure',
    'v     open CMakeCache.txt',
    'X     clean (delete) build dir',
    'R     refresh',
    'q     close',
]

SKIP = ('name', 'displayName', 'hidden', 'description', 'condition', '_file')

state = {'expanded': set(), 'buf': None, 'root': None, 'configure': [], 'build': [], 'lines': {}}


def _find_root():
    d = os.path.abspath(vim.eval('getcwd()'))
    while True:
        for f in ('CMakePresets.json', 'CMakeUserPresets.json'):
            if os.path.isfile(os.path.join(d, f)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _load(path, seen):
    path = os.path.abspath(path)
    if path in seen or not os.path.isfile(path):
        return
    seen.add(path)
    with open(path) as f:
        data = json.load(f)
    for inc in data.get('include', []):
        _load(os.path.join(os.path.dirname(path), inc), seen)
    for kind in ('configure', 'build'):
        for preset in data.get(kind + 'Presets', []):
            preset['_file'] = path
            state[kind].append(preset)


def _binary_dir(name):
    by_name = {p['name']: p for p in state['configure']}

    def find(n):
        p = by_name.get(n, {})
        if 'binaryDir' in p:
            return p['binaryDir']
        inherits = p.get('inherits', [])
        for i in [inherits] if isinstance(inherits, str) else inherits:
            found = find(i)
            if found:
                return found
        return None

    d = find(name)
    if not d:
        return None
    d = d.replace('${sourceDir}', state['root']).replace('${presetName}', name)
    return os.path.join(state['root'], d)


def _fmt(value):
    if isinstance(value, dict) and 'value' in value:
        value = value['value']
    if isinstance(value, list):
        return ', '.join(str(v) for v in value)
    return str(value)


def _details(preset):
    out = []
    for key, value in preset.items():
        if key in SKIP:
            continue
        if isinstance(value, dict):
            out.append('    %s:' % key)
            out += ['      %s=%s' % (k, _fmt(v)) for k, v in value.items()]
        else:
            out.append('    %s: %s' % (key, _fmt(value)))
    return out


def _window():
    return int(vim.eval('bufwinnr(%d)' % state['buf'])) if state['buf'] else -1


def refresh():
    state.update(configure=[], build=[], lines={})
    state['root'] = _find_root()
    lines = [TITLE, '']
    if not state['root']:
        lines.append('No CMakePresets.json found')
    else:
        try:
            seen = set()
            for f in ('CMakePresets.json', 'CMakeUserPresets.json'):
                _load(os.path.join(state['root'], f), seen)
        except ValueError as e:
            lines.append('Error: %s' % e)
        for kind, title in (('configure', 'Configure'), ('build', 'Build')):
            presets = [p for p in state[kind] if not p.get('hidden')]
            if not presets:
                continue
            lines += [title, '']
            for p in presets:
                key = (kind, p['name'])
                opened = key in state['expanded']
                default = ' (default)' if p['name'] == 'default' else ''
                state['lines'][len(lines) + 1] = key
                source = os.path.splitext(os.path.basename(p['_file']))[0]
                lines.append('%s %s%s [%s]' % ('-' if opened else '+',
                                               p.get('displayName', p['name']),
                                               default, source))
                if opened:
                    for d in _details(p):
                        state['lines'][len(lines) + 1] = key
                        lines.append(d)
            lines.append('')
    pad = max(1, vim.current.window.height - len(lines) - len(HELP))
    lines += [''] * pad + HELP
    vim.current.buffer.options['modifiable'] = True
    vim.current.buffer[:] = lines
    vim.current.buffer.options['modifiable'] = False


def toggle():
    win = _window()
    if win != -1:
        vim.command('%dwincmd c' % win)
        return
    vim.command('botright vertical 32new')
    vim.command('setlocal buftype=nofile bufhidden=wipe noswapfile nobuflisted '
                'nowrap nonumber norelativenumber winfixwidth cursorline')
    vim.command('file [CMake Presets]')
    state['buf'] = vim.current.buffer.number
    for key, arg in (('B', "'build'"), ('C', "'configure'")):
        vim.command("nnoremap <buffer> <silent> %s :py3 cmake_presets.run(%s)<CR>"
                    % (key, arg))
    vim.command('nnoremap <buffer> <silent> <CR> :py3 cmake_presets.expand()<CR>')
    vim.command('nnoremap <buffer> <silent> <LeftMouse> '
                '<LeftMouse>:py3 cmake_presets.expand()<CR>')
    vim.command('nnoremap <buffer> <silent> o :py3 cmake_presets.edit()<CR>')
    vim.command('nnoremap <buffer> <silent> v :py3 cmake_presets.open_cache()<CR>')
    vim.command('nnoremap <buffer> <silent> X :py3 cmake_presets.clean()<CR>')
    vim.command('nnoremap <buffer> <silent> R :py3 cmake_presets.refresh()<CR>')
    vim.command('nnoremap <buffer> <silent> q :close<CR>')
    vim.command('syntax match CMakePresetsHeader /^\\(Configure\\|Build\\)$/')
    vim.command(r'syntax match CMakePresetsDefault /^[+-] .*(default) \[[^]]*\]$/')
    vim.command(r'syntax match CMakePresetsSource / \[[^]]*\]$/')
    vim.command('highlight default link CMakePresetsSource Comment')
    vim.command(r'syntax match CMakePresetsFlag /^    \zs\w\+\ze:/')
    vim.command(r'syntax match CMakePresetsVar /^      \zs[^=]\+\ze=/')
    vim.command('highlight default CMakePresetsFlag ctermfg=cyan guifg=cyan')
    vim.command('highlight default CMakePresetsVar ctermfg=yellow guifg=yellow')
    vim.command('highlight default link CMakePresetsHeader Title')
    vim.command('highlight default CMakePresetsDefault ctermfg=red guifg=red')
    refresh()


def run(action):
    entry = state['lines'].get(int(vim.eval('line(".")')))
    if not entry:
        return
    kind, name = entry
    build = next((b for b in state['build'] if b['name'] == name), None) \
        if kind == 'build' else None
    cfg = build.get('configurePreset', name) if build else name
    if action == 'configure':
        cmd = ['cmake', '--preset', cfg]
    elif build:
        cmd = ['cmake', '--build', '--preset', name]
    else:
        match = [b['name'] for b in state['build'] if b.get('configurePreset') == name]
        bdir = _binary_dir(name)
        if match:
            cmd = ['cmake', '--build', '--preset', match[0]]
        elif bdir:
            cmd = ['cmake', '--build', bdir]
        else:
            vim.command('echoerr "No build preset or binaryDir for %s"' % name)
            return
    vim.command('botright 15new')
    vim.Function('term_start')(cmd, {'curwin': 1, 'cwd': state['root']})


def expand():
    entry = state['lines'].get(int(vim.eval('line(".")')))
    if not entry:
        return
    state['expanded'] ^= {entry}
    row = vim.current.window.cursor[0]
    while row > 1 and state['lines'].get(row - 1) == entry:
        row -= 1
    refresh()
    vim.current.window.cursor = (row, 0)


def _open(path):
    vim.command('wincmd h')
    if vim.current.buffer.number == state['buf']:
        vim.command('leftabove vsplit')
    vim.command('edit ' + vim.eval('fnameescape(%r)' % path))


def open_cache():
    entry = state['lines'].get(int(vim.eval('line(".")')))
    if not entry:
        return
    kind, name = entry
    if kind == 'build':
        name = next(b for b in state['build']
                    if b['name'] == name).get('configurePreset', name)
    bdir = _binary_dir(name)
    path = bdir and os.path.join(bdir, 'CMakeCache.txt')
    if path and os.path.isfile(path):
        _open(path)
    else:
        vim.command('echo "No CMakeCache.txt for preset %s (configure it first)"' % name)


def edit():
    entry = state['lines'].get(int(vim.eval('line(".")')))
    if not entry:
        return
    kind, name = entry
    preset = next(p for p in state[kind] if p['name'] == name)
    _open(preset['_file'])
    vim.command('normal! gg')
    vim.Function('search')(r'"%sPresets"' % kind)
    vim.Function('search')(r'"name"\s*:\s*"%s"' % name)


def ask(prompt):
    vim.vars['cmake_presets_prompt'] = prompt + ' (y/N) '
    return vim.eval('input(g:cmake_presets_prompt)').lower() == 'y'


def clean():
    entry = state['lines'].get(int(vim.eval('line(".")')))
    if not entry:
        return
    kind, name = entry
    if kind == 'build':
        name = next(b for b in state['build']
                    if b['name'] == name).get('configurePreset', name)
    bdir = _binary_dir(name)
    if not bdir or not os.path.isfile(os.path.join(bdir, 'CMakeCache.txt')):
        vim.command('echo "Nothing to clean for preset %s"' % name)
        return
    if os.path.realpath(state['root']).startswith(os.path.realpath(bdir)):
        vim.command('echoerr "Refusing to delete the source tree"')
        return
    if ask('Delete %s ?' % bdir):
        shutil.rmtree(bdir)
        vim.command('echo "Deleted %s"' % bdir.replace('"', ''))
