# Xbox Input → XInput Compatibility Layer

add_library(xbox_input STATIC
    xinput_device.c
)
if(NINTENDO_SWITCH)
    # The Switch's controllers, read through libnx and mapped by position.
    target_sources(xbox_input PRIVATE xinput_nx.c)
endif()

target_include_directories(xbox_input PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(WIN32 AND NOT XBOXRECOMP_WIN_GL)
    target_link_libraries(xbox_input PUBLIC platform xinput)
else()
    # SDL2 GameController + keyboard: Linux, the Switch, and Windows builds
    # with an SDL window (XBOXRECOMP_WIN_GL), whose keys the GDI window path
    # of the XInput branch never sees.
    if(WIN32)
        target_compile_definitions(xbox_input PRIVATE XBOXRECOMP_SDL_INPUT=1)
    endif()
    find_package(SDL2 REQUIRED)
    target_sources(xbox_input PRIVATE sdl_keys.c)   # keyboard as pad 1 (PC)
    target_link_libraries(xbox_input PUBLIC platform SDL2::SDL2)
endif()

if(MSVC)
    target_compile_options(xbox_input PRIVATE /W4 /O2)
else()
    target_compile_options(xbox_input PRIVATE -Wall -Wextra -O2)
endif()
