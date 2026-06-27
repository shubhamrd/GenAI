## **Serverless AI DevOps Log Analyzer - Complete Guide**

This guide walks you through building a fully serverless web application that uses **Amazon Bedrock (Nova Lite)** to analyze and diagnose DevOps error logs.

**Architecture Overview:** `S3 (Frontend)` → `API Gateway (REST API with API Key)` → `AWS Lambda (Python Engine)` → `Amazon Bedrock (AI Model)`.

![Architecture Diagram](images/log-analyzer-arch.png)


### **Phase 1: IAM Role & Permissions**

Before creating the Lambda function, it needs an IAM Role with a specific inline policy to invoke Amazon Bedrock and write logs to CloudWatch.

1. Go to the IAM Console → Roles → Create role.
2. Select AWS service → Lambda → click **Next**.
3. Do not select any policies on this screen. Click **Next**.
4. Role name: `LogAnalyzerLambdaRole`. Click **Create role**.
5. Find and click on your new `LogAnalyzerLambdaRole` in the list to open it.
6. Under the **Permissions** tab, click **Add permissions** → **Create inline policy**.
7. Switch to the **JSON** tab and paste the following strict policy:

   ```json
   {
   	"Version": "2012-10-17",
   	"Statement": [
   		{
   			"Sid": "BedrockInvokePermission",
   			"Effect": "Allow",
   			"Action": "bedrock:InvokeModel",
   			"Resource": "*"
   		},
   		{
   			"Sid": "CloudWatchLoggingPermissions",
   			"Effect": "Allow",
   			"Action": [
   				"logs:CreateLogGroup",
   				"logs:CreateLogStream",
   				"logs:PutLogEvents"
   			],
   			"Resource": "arn:aws:logs:*:*:*"
   		}
   	]
   }
   ```

8. Click **Next**, name the policy `BedrockAndCloudWatchAccess`, and click **Create policy**.

### **Phase 2: The AI Engine (AWS Lambda)**

1. Go to the AWS Lambda Console → Create function.
2. Choose **Author from scratch**.
3. Function name: `DevOpsLogAnalyzerEngine`
4. Runtime: Python 3.12 (or latest)
5. Execution role: Select **"Use an existing role"** and choose `LogAnalyzerLambdaRole`.
6. Click **Create function**.
7. In the **Code source** editor, paste the following Python code. This formats the prompt and calls Amazon Bedrock.

   ```python
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
   ```

8. Click **Deploy** to save the code.
9. Go to the **Configuration** tab → **General configuration** → **Edit**. Increase the **Timeout** to 45 seconds. Click **Save**.

### **Phase 3: Secure API Gateway (API Key Method)**

We need a front door to our Lambda function, secured so that only authorized users (our web app) can trigger it.

#### **Step 3.1: Create the API and Resource**

1. Navigate to the Amazon API Gateway Console → Create API.
2. Select **REST API** (Not Private) and click **Build**.
3. Name it `LogAnalyzerSecureGateway` and click **Create API**.
4. Click **Create resource**, set the path to `analyze`, and click **Create resource**.

#### **Step 3.2: Create the POST Method**

1. Select the `/analyze` resource and click **Create method**.
2. Method type: **POST**
3. Integration type: **Lambda function**
4. Lambda proxy integration: Toggle to **ON** (Critical).
5. Lambda function: Select `DevOpsLogAnalyzerEngine`.
6. Click **Create method**.

#### **Step 3.3: Enable CORS**

1. Select the `/analyze` resource.
2. Click **Enable CORS**.
3. Check the boxes for **POST** and **OPTIONS**.
4. Click **Save**.

#### **Step 3.4: Require an API Key**

1. Click on the **POST** method under `/analyze`.
2. Go to **Method Request**.
3. Set **API Key Required** to **true**.

#### **Step 3.5: Deploy the API**

1. Click the **Deploy API** button.
2. Create a new stage named `prod`.
3. Click **Deploy**. (Note your Invoke URL, e.g., `https://i622komjy7.execute-api.us-east-1.amazonaws.com/prod`)

#### **Step 3.6: Create Usage Plan & Associate the Key**

1. In the left menu, click **Usage Plans** → **Create usage plan**.
2. Name: `LogAnalyzerPlan`
3. Rate: `10`, Burst: `5`, Quota: `1000` per Month. Click **Next**.
4. Associated API Stages: Click **Add API Stage**. Select your API and the `prod` stage. Click **Next**.
5. Usage Plan API Keys: Click **Add API Key to Usage Plan** → **Create an API Key**.
6. Name it `DemoKey`, click **Save**, then click **Done**.
7. Navigate to **API Keys** in the left menu, click your key, click **Show**, and copy the API Key string.

> **⚠️ CRITICAL: Redeploy Your API**
> 
> After creating the Usage Plan and API Key, go back to your API → Resources → **Deploy API**
> 
> After creating the Usage Plan and API Key, go back to your API → Resources → **Deploy API** again to ensure the Usage Plan association is fully propagated to the prod stage.

### **Checkpoint 3.7: Network Security Testing**

1. Run this in Git Bash to test your secured endpoint (replace the URL and API key with your own):

   Replace `YOUR_API_ENDPOINT` and `YOUR_API_KEY` with your actual values.

   ```bash
   curl -X POST YOUR_API_ENDPOINT \
     -H "Content-Type: application/json" \
     -H "x-api-key: YOUR_API_KEY" \
     -d '{"log": "FATAL: OutOfMemoryError Java heap space"}'
   ```

### **Phase 4: Deploy the Secure Web Interface (Amazon S3)**

We will host a single HTML file on a fully private S3 bucket and access it via a temporary session URL.

#### **Step 4.1: Create the S3 Bucket**

1. Open the Amazon S3 Console → Create bucket.
2. Provide a unique name (e.g., `devops-demo-ui-123`).
3. Leave **Block all public access** turned ON (The bucket stays strictly private).
4. Click **Create bucket**.

#### **Step 4.2: Create the HTML File**

1. Create a file on your computer named `index.html`. Paste the code below.

> **⚠️ IMPORTANT: Configure API Credentials Before Uploading**
> 
> In the `<script>` section of the HTML code below, you'll find two variables that need to be updated:
> 
> ```javascript
> const API_ENDPOINT = "YOUR_API_ENDPOINT_HERE"; // ✏️ REPLACE WITH YOUR API GATEWAY URL
> const API_KEY = "YOUR_API_KEY_HERE"; // ✏️ REPLACE WITH YOUR API KEY
> ```
> 
> **To find these values:**
> - **API Endpoint**: Go to API Gateway → Stages → Select your stage → Copy the invoke URL
> - **API Key**: Go to API Gateway → Usage Plans → Select your plan → Show API Key
> 
> **Failure to update these values will cause connection errors** when users try to analyze logs.

<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DevOps Log Analyzer</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }

        .app-card {
            max-width: 850px;
            margin: 0 auto;
            background: #fff;
            padding: 50px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
            animation: fadeIn 0.6s ease-out;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .header {
            text-align: center;
            margin-bottom: 35px;
        }

        .header h1 {
            font-size: 2.2rem;
            color: #2d3748;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
        }

        .header h1 i {
            color: #667eea;
        }

        .creator {
            text-align: center;
            color: #718096;
            font-size: 0.9rem;
            margin-bottom: 30px;
            padding-top: 15px;
            border-top: 1px solid #e2e8f0;
        }

        .creator span {
            color: #667eea;
            font-weight: 600;
        }

        .input-section {
            margin-bottom: 25px;
        }

        .input-label {
            display: block;
            margin-bottom: 12px;
            color: #4a5568;
            font-weight: 600;
            font-size: 0.95rem;
        }

        textarea {
            width: 100%;
            height: 180px;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 0.9rem;
            padding: 18px;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            resize: vertical;
            transition: all 0.3s ease;
            background: #f8fafc;
        }

        textarea:focus {
            outline: none;
            border-color: #667eea;
            background: #fff;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .button-group {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            margin-top: 20px;
        }

        .btn {
            flex: 1;
            min-width: 180px;
            padding: 14px 28px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        }

        .btn-secondary {
            background: #f7fafc;
            color: #4a5568;
            border: 2px solid #e2e8f0;
        }

        .btn-secondary:hover {
            background: #edf2f7;
            border-color: #cbd5e0;
            transform: translateY(-2px);
        }

        .output-section {
            margin-top: 35px;
            padding: 30px;
            background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
            border-radius: 16px;
            border: 2px solid #e2e8f0;
            display: none;
            animation: slideUp 0.4s ease-out;
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .output-section.active {
            display: block;
        }

        .output-section h3 {
            color: #2d3748;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .output-section h3 i {
            color: #667eea;
        }

        .result-card {
            background: #fff;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 15px;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        }

        .result-card.cause {
            border-left-color: #f56565;
        }

        .result-card.remediation {
            border-left-color: #48bb78;
        }

        .result-label {
            font-size: 0.8rem;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
            display: block;
        }

        .result-value {
            color: #2d3748;
            line-height: 1.6;
            font-size: 0.95rem;
        }

        .remediation-list {
            padding-left: 20px;
            color: #4a5568;
        }

        .remediation-list li {
            margin-bottom: 8px;
            line-height: 1.5;
        }
    </style>
</head>

<body>
    <div class="app-card">
        <div class="header">
            <h1><i class="fas fa-robot"></i> DevOps Log Analyzer</h1>
        </div>
        
        <div class="input-section">
            <label class="input-label" for="logContainer"><i class="fas fa-clipboard-list"></i> Paste Log Output</label>
            <textarea id="logContainer" placeholder="Paste your log entries here for analysis..."></textarea>
        </div>

        <div class="button-group">
            <button class="btn btn-primary" onclick="processLogStream()">
                <i class="fas fa-magnifying-glass"></i> Run Diagnostics
            </button>
            <button class="btn btn-secondary" onclick="loadDemoLog()">
                <i class="fas fa-dice"></i> Load Demo Log
            </button>
        </div>

        <div class="creator">
            Created by <span>Shubham Dalvi</span>
        </div>

        <div id="outputGrid" class="output-section">
            <h3><i class="fas fa-chart-pie"></i> Analysis Results</h3>
            <div id="summaryField"></div>
            <div id="rootCauseField"></div>
            <div id="remediationField"></div>
        </div>
    </div>

    <script>
        const API_ENDPOINT = "YOUR_API_ENDPOINT_HERE"; // REPLACE WITH YOUR API GATEWAY URL (e.g., https://xyz.execute-api.us-east-1.amazonaws.com/prod/analyze)
        const API_KEY = "YOUR_API_KEY_HERE"; // REPLACE WITH YOUR API KEY FROM API GATEWAY

        const demoLogs = [
            "2026-06-26T14:10:22Z ERROR org.postgresql.Driver - Connection refused to host: database.internal:5432. java.net.ConnectException: Connection timed out",
            "2026-06-26T15:23:45Z ERROR com.example.api.UserService - Failed to authenticate user: java.lang.SecurityException - Invalid token provided for user ID: 12345",
            "2026-06-26T16:45:12Z ERROR org.apache.kafka.clients.producer.Producer - Failed to send message to topic 'orders': org.apache.kafka.common.errors.TimeoutException - Exceeded max block time of 60000 ms",
            "2026-06-26T17:12:33Z ERROR com.example.cache.RedisCache - Redis connection failed: java.net.NoRouteToHostException - No route to host: redis.internal:6379",
            "2026-06-26T18:30:00Z ERROR com.example.service.PaymentGateway - Payment processing failed: com.stripe.exception.CardException - Your card was declined.",
            "2026-06-26T19:45:22Z ERROR org.quartz.core.JobThread - Job execution failed: java.lang.NullPointerException - Cannot invoke method on null object in class ReportGenerator",
            "2026-06-26T20:15:45Z ERROR com.example.auth.OAuth2Service - Token refresh failed: java.io.IOException - Connection reset by peer",
            "2026-06-26T21:30:11Z ERROR org.springframework.web.client.RestTemplate - HTTP 503 Service Unavailable: Service 'user-service' is not available"
        ];

        function loadDemoLog() {
            const randomIndex = Math.floor(Math.random() * demoLogs.length);
            document.getElementById('logContainer').value = demoLogs[randomIndex];
        }

        async function processLogStream() {
            const streamData = document.getElementById('logContainer').value;
            const viewGrid = document.getElementById('outputGrid');

            try {
                const response = await fetch(API_ENDPOINT, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "x-api-key": API_KEY
                    },
                    body: JSON.stringify({ log: streamData })
                });

                const result = await response.json();
                
                // Check for API-specific errors
                if (!response.ok) {
                    throw new Error(`API Error ${response.status}: ${JSON.stringify(result)}`);
                }
                
                // Display summary
                document.getElementById('summaryField').innerHTML = `
                    <div class="result-card">
                        <span class="result-label"><i class="fas fa-clipboard-check"></i> Error Summary</span>
                        <div class="result-value">${result.error_summary}</div>
                    </div>
                `;
                
                // Display root cause
                document.getElementById('rootCauseField').innerHTML = `
                    <div class="result-card cause">
                        <span class="result-label"><i class="fas fa-magnifying-glass-chart"></i> Root Cause</span>
                        <div class="result-value">${result.root_cause}</div>
                    </div>
                `;
                
                // Display remediation steps if available
                const remediationField = document.getElementById('remediationField');
                if (result.remediation_steps && result.remediation_steps.length > 0) {
                    let stepsHTML = '<div class="result-card remediation"><span class="result-label"><i class="fas fa-list-check"></i> Remediation Steps</span><ul class="remediation-list">';
                    result.remediation_steps.forEach(step => {
                        stepsHTML += `<li>${step}</li>`;
                    });
                    stepsHTML += '</ul></div>';
                    remediationField.innerHTML = stepsHTML;
                } else {
                    remediationField.innerHTML = '';
                }
                
                viewGrid.classList.add('active');
            } catch (e) {
                alert("Error: " + e.message + "\n\nThis is likely a CORS issue. The API Gateway needs CORS enabled to allow requests from your S3-hosted page.\n\nSolution: Enable CORS on API Gateway → Methods → /prod/analyze → Enable CORS");
            }
        }
        
        // Add hover animation to buttons
        document.querySelectorAll('.btn').forEach(btn => {
            btn.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-2px)';
            });
            
            btn.addEventListener('mouseleave', function() {
                this.style.transform = 'translateY(0)';
            });
        });
    </script>
</body>

</html>