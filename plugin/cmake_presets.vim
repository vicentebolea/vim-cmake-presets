if exists('g:loaded_cmake_presets') || !has('python3')
  finish
endif
let g:loaded_cmake_presets = 1

command! CMakePresets py3 import cmake_presets; cmake_presets.toggle()
