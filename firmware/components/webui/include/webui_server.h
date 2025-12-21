#pragma once

#include "esp_err.h"
#include "esp_http_server.h"

/**
 * @brief Initialize the Web UI server
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t webui_server_init(void);

/**
 * @brief Start the HTTP server
 * 
 * @return httpd_handle_t Handle to the server
 */
httpd_handle_t webui_server_start(void);

/**
 * @brief Stop the HTTP server
 * 
 * @param server Server handle
 */
void webui_server_stop(httpd_handle_t server);
