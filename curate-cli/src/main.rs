use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::io::{self, Read, Write};

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
struct InputPayload {
    operation: String,
    base_url: String,
    token: String,
    payload: Option<serde_json::Value>,
}

#[derive(Serialize)]
struct ErrorResponse {
    status: String,
    message: String,
}

fn main() {
    if let Err(e) = run() {
        let err_resp = ErrorResponse {
            status: "error".to_string(),
            message: e.to_string(),
        };
        // Print error as JSON so the TS node can parse it
        let _ = writeln!(io::stdout(), "{}", serde_json::to_string(&err_resp).unwrap());
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    // Read stdin
    let mut input_str = String::new();
    io::stdin().read_to_string(&mut input_str).context("Failed to read stdin")?;

    let input: InputPayload = serde_json::from_str(&input_str).context("Failed to parse JSON input")?;

    let client = reqwest::blocking::Client::new();
    let mut base_url = input.base_url.trim_end_matches('/').to_string();
    if base_url.is_empty() {
        base_url = "http://localhost:8000".to_string();
    }

    let response = if input.operation == "transform" {
        let url = format!("{}/v1/transform", base_url);
        let payload = input.payload.context("Missing payload for transform operation")?;
        
        client
            .post(&url)
            .header("Authorization", format!("Bearer {}", input.token))
            .json(&payload)
            .send()
            .context("Failed to send transform request")?
    } else if input.operation == "getUsage" {
        let url = format!("{}/v1/usage", base_url);
        
        client
            .get(&url)
            .header("Authorization", format!("Bearer {}", input.token))
            .send()
            .context("Failed to send getUsage request")?
    } else {
        anyhow::bail!("Unknown operation: {}", input.operation);
    };

    let status = response.status();
    let text = response.text().context("Failed to read response body")?;

    if !status.is_success() {
        anyhow::bail!("API Error ({}): {}", status, text);
    }

    // Try to parse the response as JSON to ensure it's valid
    let _: serde_json::Value = serde_json::from_str(&text).context(format!("API returned invalid JSON: {}", text))?;

    // Write successful response to stdout
    println!("{}", text);

    Ok(())
}
