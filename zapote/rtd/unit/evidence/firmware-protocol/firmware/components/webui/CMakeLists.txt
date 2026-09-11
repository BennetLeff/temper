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
                       PRIV_REQUIRES esp_http_server esp_vfs_fat json
                       EMBED_FILES ${webui_embed_files})
