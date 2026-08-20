set(webui_srcs
    "server.c"
)

set(webui_embed_files
    "static/index.html"
    "static/style.css"
    "static/script.js"
)

idf_component_register(SRCS ${webui_srcs}
                       INCLUDE_DIRS "include"
                       # `fatfs` is the IDF component name; `esp_vfs_fat`
                       # is the *header* directory and is not resolvable as
                       # a component, which made this an unconditional
                       # configure-time failure:
                       #   CMake Error: Failed to resolve component 'esp_vfs_fat'.
                       # NOTE for maintainers: server.c currently includes no
                       # FAT/VFS header (it serves its assets via EMBED_FILES),
                       # so this dependency is declared but unused. It is kept
                       # under the corrected name rather than dropped, because
                       # removing a declared dependency is a decision about
                       # intent that belongs to the webui author.
                       PRIV_REQUIRES esp_http_server fatfs json
                       EMBED_FILES ${webui_embed_files})
