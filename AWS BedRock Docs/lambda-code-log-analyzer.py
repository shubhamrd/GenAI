import json
import boto3
import os
import re

REG_NAME = os.environ.get("AWS_REGION", "us-east-1")

# Switched to Amazon Nova Lite (Using the required Cross-Region prefix)
MODEL_ID = "us.amazon.nova-lite-v1:0" 
bedrock_runtime = boto3.client("bedrock-runtime", region_name=REG_NAME)

def lambda_handler(event, context):
    try:
        # Extract payload safely
        body = event.get("body", "") if isinstance(event, dict) else event
        if not body:
            body = event
            
        if isinstance(body, str):
            try:
                data = json.loads(body)
                raw_log = data.get("log", body)
            except json.JSONDecodeError:
                raw_log = body
        else:
            raw_log = body.get("log", str(body))

        # Nova responds very well to strict system instructions
        system_instruction = (
            "You are an expert DevOps engineer. Analyze the log. "
            "Output ONLY valid JSON. "
            "Schema: {\"error_summary\": \"...\", \"root_cause\": \"...\", \"remediation_steps\": [\"...\", \"...\"]}"
        )

        messages = [{"role": "user", "content": [{"text": f"Analyze this log:\n{raw_log}"}]}]

        # Invoke Bedrock using the Converse API
        response = bedrock_runtime.converse(
            modelId=MODEL_ID,
            messages=messages,
            system=[{"text": system_instruction}],
            inferenceConfig={
                "maxTokens": 500, 
                "temperature": 0.1, 
                "topP": 0.9
            }
        )

        ai_response_text = response['output']['message']['content'][0]['text']
        
        # BULLETPROOF JSON EXTRACTION
        json_match = re.search(r'\{.*\}', ai_response_text, re.DOTALL)
        
        if not json_match:
            raise ValueError(f"No JSON found in model output. Raw output was: {ai_response_text}")
            
        clean_json_string = json_match.group(0)
        parsed_json = json.loads(clean_json_string)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type"
            },
            "body": json.dumps(parsed_json)
        }

    except Exception as e:
        print(f"System Failure: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Failed to parse log entry", "details": str(e)})
        }