cmake_minimum_required(VERSION 3.20.0)

if(BOARD STREQUAL "nucleo_h7a3zi_q")
    set(BOARD_FLASH_RUNNER openocd)
endif()

set(DTC_OVERLAY_FILE ${CMAKE_CURRENT_SOURCE_DIR}/../common/boards/${BOARD}.overlay)
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/../common/boards/${BOARD}.conf)
    set(EXTRA_CONF_FILE ${CMAKE_CURRENT_SOURCE_DIR}/../common/boards/${BOARD}.conf)
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(mlperf_tiny_ic02)

set(MODEL_DIR ${CMAKE_CURRENT_SOURCE_DIR}/model/${BOARD})
if(NOT EXISTS "${MODEL_DIR}/lib/libmodel.a")
    message(FATAL_ERROR "Missing ${MODEL_DIR}/lib/libmodel.a")
endif()

target_sources(app PRIVATE
    src/submitter_implemented.cpp
    ${CMAKE_SOURCE_DIR}/../common/main.cpp
    ${CMAKE_SOURCE_DIR}/../common/internally_implemented.cpp
    ${CMAKE_SOURCE_DIR}/../common/dwt_timestamp.cpp
    ${CMAKE_SOURCE_DIR}/../common/eembc_shim.cpp
)

target_include_directories(app PRIVATE
    ${CMAKE_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/../..
    ${MODEL_DIR}/include
)

target_link_libraries(app PRIVATE ${MODEL_DIR}/lib/libmodel.a)
