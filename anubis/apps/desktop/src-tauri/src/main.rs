use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Debug, Deserialize, Serialize)]
struct ChatBridgeRequest {
    conversation_id: Option<String>,
    message: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct ChatBridgeResponse {
    conversation_id: String,
    message: serde_json::Value,
    sources: Vec<serde_json::Value>,
    tool_logs: Vec<serde_json::Value>,
    request_id: String,
}

#[tauri::command]
async fn send_chat_message(request: ChatBridgeRequest) -> Result<ChatBridgeResponse, String> {
    let base_url = std::env::var("ANUBIS_AI_CORE_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8100".to_string());
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(35))
        .build()
        .map_err(|error| error.to_string())?;

    let response = client
        .post(format!("{}/v1/chat", base_url.trim_end_matches('/')))
        .header("x-request-id", uuid::Uuid::new_v4().to_string())
        .json(&request)
        .send()
        .await
        .map_err(|error| error.to_string())?;

    if !response.status().is_success() {
        return Err(format!("AI Core returned {}", response.status()));
    }

    response
        .json::<ChatBridgeResponse>()
        .await
        .map_err(|error| error.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![send_chat_message])
        .run(tauri::generate_context!())
        .expect("failed to run Anubis desktop");
}
