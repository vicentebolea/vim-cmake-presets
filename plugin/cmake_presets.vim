if exists('g:loaded_cmake_presets') || !has('python3')
  finish
endif
let g:loaded_cmake_presets = 1

command! CMakePresets py3 import cmake_presets; cmake_presets.toggle()

let g:cmake_presets_map = get(g:, 'cmake_presets_map', '<F8>')
if !empty(g:cmake_presets_map)
  execute 'nnoremap <silent>' g:cmake_presets_map ':CMakePresets<CR>'
endif
