#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_http_server.h"
#include "webui_server.h"

static const char *TAG = "WEBUI";

/* Embedded file pointers */
extern const uint8_t index_html_start[] asm("_binary_index_html_start");
extern const uint8_t index_html_end[]   asm("_binary_index_html_end");
extern const uint8_t style_css_start[]  asm("_binary_style_css_start");
extern const uint8_t style_css_end[]    asm("_binary_style_css_end");
extern const uint8_t script_js_start[]  asm("_binary_script_js_start");
extern const uint8_t script_js_end[]    asm("_binary_script_js_end");

/* GET / handler */
static esp_err_t index_get_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, (const char *)index_html_start, index_html_end - index_html_start);
    return ESP_OK;
}

/* GET /style.css handler */
static esp_err_t style_get_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/css");
    httpd_resp_send(req, (const char *)style_css_start, style_css_end - style_css_start);
    return ESP_OK;
}

/* GET /script.js handler */
static esp_err_t script_get_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "application/javascript");
    httpd_resp_send(req, (const char *)script_js_start, script_js_end - script_js_start);
    return ESP_OK;
}

/* API Status handler */
static esp_err_t api_status_get_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "application/json");
    const char *resp = "{\"status\": \"idle\", \"temp\": 25.0, \"target\": 100.0}";
    httpd_resp_send(req, resp, strlen(resp));
    return ESP_OK;
}

static const httpd_uri_t index_uri = {
    .uri       = "/",
    .method    = HTTP_GET,
    .handler   = index_get_handler,
};

static const httpd_uri_t style_uri = {
    .uri       = "/style.css",
    .method    = HTTP_GET,
    .handler   = style_get_handler,
};

static const httpd_uri_t script_uri = {
    .uri       = "/script.js",
    .method    = HTTP_GET,
    .handler   = script_get_handler,
};

static const httpd_uri_t api_status_uri = {
    .uri       = "/api/status",
    .method    = HTTP_GET,
    .handler   = api_status_get_handler,
};

httpd_handle_t webui_server_start(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    httpd_handle_t server = NULL;

    ESP_LOGI(TAG, "Starting server on port: '%d'", config.server_port);
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_register_uri_handler(server, &index_uri);
        httpd_register_uri_handler(server, &style_uri);
        httpd_register_uri_handler(server, &script_uri);
        httpd_register_uri_handler(server, &api_status_uri);
        return server;
    }

    ESP_LOGE(TAG, "Error starting server!");
    return NULL;
}

void webui_server_stop(httpd_handle_t server) {
    if (server) {
        httpd_stop(server);
    }
}
