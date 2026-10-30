cmake_minimum_required(VERSION 3.20)
project(nv2a_vk C)

# Vulkan 1.3 renderer for the pushbuffer executor (XBOXRECOMP_VULKAN=ON):
# the Switch's NVK from mesa-switch, linked statically (NVK_SDK), or any
# Vulkan driver on Linux. Shares the shader generators with nv2a_gl, in
# their Vulkan dialect, and compiles them with glslang at run time.
add_library(xbox_nv2a_vk STATIC
    nv2a_vk.c
    ../nv2a_gl/gl_vsh.c
    ../nv2a_gl/gl_psh.c
)
target_include_directories(xbox_nv2a_vk PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

find_package(glslang CONFIG REQUIRED)
target_link_libraries(xbox_nv2a_vk PUBLIC glslang::glslang glslang::glslang-default-resource-limits)

if(NINTENDO_SWITCH)
    set(NVK_SDK "" CACHE PATH "mesa-switch install prefix (holds lib/libvulkan.a, include/vulkan)")
    if(NOT EXISTS "${NVK_SDK}/lib/libvulkan.a")
        message(FATAL_ERROR "NVK_SDK must point at a mesa-switch install (no lib/libvulkan.a in '${NVK_SDK}')")
    endif()
    target_include_directories(xbox_nv2a_vk PUBLIC "${NVK_SDK}/include")
    target_sources(xbox_nv2a_vk PRIVATE switch_elf_stubs.c switch_egl_stubs.c)
    # Static NVK and what it needs; listed twice for archive rescanning.
    target_link_libraries(xbox_nv2a_vk PUBLIC
        "${NVK_SDK}/lib/libvulkan.a" expat zstd z nx
        "${NVK_SDK}/lib/libvulkan.a" expat zstd z nx stdc++ m)
elseif(ANDROID)
    # SDL2 from android/build_deps.sh. glslang is built there without its
    # optimizer; its SPIR-V output (glslang_program_SPIRV_*) is a library of
    # its own. Vulkan comes through volk: the system's libvulkan.so, or a
    # custom driver (Mesa Turnip) that libadrenotools loads; its hook
    # libraries (libmain_hook.so, ...) go into the APK next to libmain.so.
    set(VOLK_DIR "" CACHE PATH "volk source (android/build_deps.sh)")
    set(ADRENOTOOLS_DIR "" CACHE PATH "libadrenotools source (android/build_deps.sh)")
    if(NOT EXISTS "${VOLK_DIR}/volk.c" OR NOT EXISTS "${ADRENOTOOLS_DIR}/CMakeLists.txt")
        message(FATAL_ERROR "VOLK_DIR and ADRENOTOOLS_DIR must point at volk and libadrenotools (android/build_deps.sh)")
    endif()
    add_subdirectory("${ADRENOTOOLS_DIR}" adrenotools)
    foreach(hook hook_impl main_hook file_redirect_hook gsl_alloc_hook)
        target_link_options(${hook} PRIVATE "-Wl,-z,max-page-size=16384")
    endforeach()
    target_sources(xbox_nv2a_vk PRIVATE "${VOLK_DIR}/volk.c")
    target_include_directories(xbox_nv2a_vk PUBLIC "${VOLK_DIR}")
    target_compile_definitions(xbox_nv2a_vk PUBLIC VK_USE_PLATFORM_ANDROID_KHR=1)
    add_dependencies(xbox_nv2a_vk main_hook file_redirect_hook gsl_alloc_hook)
    find_package(SDL2 REQUIRED)
    target_link_libraries(xbox_nv2a_vk PUBLIC glslang::SPIRV SDL2::SDL2 adrenotools dl c++_static c++abi)
else()
    find_package(Vulkan REQUIRED)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(SDL2 REQUIRED IMPORTED_TARGET sdl2)
    # The distribution glslang is built with its optimizer (static SPIRV-Tools).
    target_link_libraries(xbox_nv2a_vk PUBLIC Vulkan::Vulkan PkgConfig::SDL2
        SPIRV-Tools-opt SPIRV-Tools stdc++)
endif()
if(NOT MSVC)
    target_compile_options(xbox_nv2a_vk PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers -O2)
endif()
