import { Container } from "@cloudflare/containers";

interface Env {
  PLATFORM_KV: KVNamespace;
  RATE_LIMITS: KVNamespace;
  STORAGE: R2Bucket;
  VIDEO_QUEUE: Queue;
  VECTORIZE: VectorizeIndex;
  VIDEO_PROCESSOR: DurableObjectNamespace;
  ENVIRONMENT: string;
  TURSO_PLATFORM_DB_URL?: string;
  TURSO_PLATFORM_AUTH_TOKEN?: string;
  CLERK_SECRET_KEY?: string;
  OPENROUTER_API_KEY?: string;
  ASSEMBLYAI_API_KEY?: string;  // ADD THIS
}

export class VideoProcessor extends Container {
  defaultPort = 8080;
  sleepAfter = "5m";
  
  // Note: For secrets, we'll pass them via the request instead
  // envVars only works for non-sensitive config
  envVars = {
    MAX_VIDEO_LENGTH: "3600",
  };

  override onStart(): void {
    console.log("VideoProcessor container started");
  }

  override onStop(): void {
    console.log("VideoProcessor container stopped");
  }

  override onError(error: unknown): void {
    console.error("VideoProcessor container error:", error);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };
    
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      // ========== CONTAINER ROUTES ==========
      
      if (url.pathname.startsWith("/process-video/")) {
        const jobId = url.pathname.split("/process-video/")[1];
        
        if (!jobId) {
          return Response.json(
            { error: "Job ID required" },
            { status: 400, headers: corsHeaders }
          );
        }
        
        const id = env.VIDEO_PROCESSOR.idFromName(jobId);
        const container = env.VIDEO_PROCESSOR.get(id);
        return await container.fetch(request);
      }
      
      if (url.pathname === "/test/container") {
        const testId = "test-" + Date.now();
        const id = env.VIDEO_PROCESSOR.idFromName(testId);
        const container = env.VIDEO_PROCESSOR.get(id);
        
        const containerRequest = new Request("http://container/health", {
          method: "GET",
        });
        
        try {
          const response = await container.fetch(containerRequest);
          const data = await response.json();
          
          return Response.json({
            success: true,
            test: "container",
            containerId: testId,
            containerResponse: data,
          }, { headers: corsHeaders });
        } catch (error) {
          return Response.json({
            success: false,
            test: "container",
            error: error instanceof Error ? error.message : "Container failed to respond",
            note: "Container may take 2-3 seconds to cold start on first request",
          }, { headers: corsHeaders });
        }
      }

      // ========== EXISTING ROUTES ==========
      
      if (url.pathname === "/health") {
        return Response.json({
          status: "ok",
          timestamp: new Date().toISOString(),
          environment: env.ENVIRONMENT,
          bindings: {
            kv_platform: !!env.PLATFORM_KV,
            kv_ratelimits: !!env.RATE_LIMITS,
            r2_storage: !!env.STORAGE,
            queue_video: !!env.VIDEO_QUEUE,
            vectorize: !!env.VECTORIZE,
            container_video: !!env.VIDEO_PROCESSOR,
          },
          secrets: {
            turso_url: !!env.TURSO_PLATFORM_DB_URL,
            turso_token: !!env.TURSO_PLATFORM_AUTH_TOKEN,
            clerk: !!env.CLERK_SECRET_KEY,
            openrouter: !!env.OPENROUTER_API_KEY,
            assemblyai: !!env.ASSEMBLYAI_API_KEY,
          }
        }, { headers: corsHeaders });
      }
      
      if (url.pathname === "/test/kv") {
        const testKey = "test-" + Date.now();
        await env.PLATFORM_KV.put(testKey, "Hello from KV!");
        const value = await env.PLATFORM_KV.get(testKey);
        await env.PLATFORM_KV.delete(testKey);
        return Response.json({ success: true, test: "kv", value }, { headers: corsHeaders });
      }
      
      if (url.pathname === "/test/r2") {
        const testKey = "test-file-" + Date.now() + ".txt";
        await env.STORAGE.put(testKey, "Hello from R2!");
        const object = await env.STORAGE.get(testKey);
        const text = await object?.text();
        await env.STORAGE.delete(testKey);
        return Response.json({ success: true, test: "r2", content: text }, { headers: corsHeaders });
      }
      
      if (url.pathname === "/test/queue") {
        await env.VIDEO_QUEUE.send({
          type: "test",
          timestamp: Date.now(),
          message: "Test queue message"
        });
        return Response.json({ 
          success: true, 
          test: "queue",
          message: "Message sent to queue" 
        }, { headers: corsHeaders });
      }
      
      if (url.pathname === "/test/vectorize") {
        const testVector = new Array(768).fill(0.1);
        const testId = "test-" + Date.now();
        
        await env.VECTORIZE.upsert([{
          id: testId,
          values: testVector,
          metadata: { test: true, timestamp: Date.now() }
        }]);
        
        const results = await env.VECTORIZE.query(testVector, {
          topK: 1,
          returnMetadata: true
        });
        
        await env.VECTORIZE.deleteByIds([testId]);
        
        return Response.json({ 
          success: true, 
          test: "vectorize",
          results 
        }, { headers: corsHeaders });
      }
      
      if (url.pathname === "/test/ai") {
        if (!env.OPENROUTER_API_KEY) {
          return Response.json({ 
            success: false, 
            error: "OPENROUTER_API_KEY not configured" 
          }, { status: 400, headers: corsHeaders });
        }
        
        const model = url.searchParams.get("model") || "openai/gpt-4o-mini";
        
        const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${env.OPENROUTER_API_KEY}`,
            "HTTP-Referer": "https://api.quickbizkit.ai",
            "X-Title": "Platform API Test"
          },
          body: JSON.stringify({
            model: model,
            max_tokens: 100,
            messages: [
              { role: "user", content: "Say 'API test successful!' and nothing else." }
            ]
          })
        });
        
        const data = await response.json();
        return Response.json({ 
          success: response.ok, 
          test: "ai",
          provider: "openrouter",
          model: model,
          response: data 
        }, { headers: corsHeaders });
      }

      if (url.pathname === "/test/ai/claude") {
        if (!env.OPENROUTER_API_KEY) {
          return Response.json({ 
            success: false, 
            error: "OPENROUTER_API_KEY not configured" 
          }, { status: 400, headers: corsHeaders });
        }
        
        const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${env.OPENROUTER_API_KEY}`,
            "HTTP-Referer": "https://api.quickbizkit.ai",
            "X-Title": "Platform API Test"
          },
          body: JSON.stringify({
            model: "anthropic/claude-3.5-haiku",
            max_tokens: 100,
            messages: [
              { role: "user", content: "Say 'Claude via OpenRouter test successful!' and nothing else." }
            ]
          })
        });
        
        const data = await response.json();
        return Response.json({ 
          success: response.ok, 
          test: "ai/claude",
          provider: "openrouter",
          model: "anthropic/claude-3.5-haiku",
          response: data 
        }, { headers: corsHeaders });
      }
      
      // Default response
      return Response.json({
        name: "Platform API",
        version: "1.0.0",
        endpoints: [
          "GET /health - Check all bindings",
          "GET /test/kv - Test KV storage",
          "GET /test/r2 - Test R2 storage", 
          "GET /test/queue - Test Queue",
          "GET /test/vectorize - Test Vectorize",
          "GET /test/container - Test Container (video processor)",
          "GET /test/ai - Test AI via OpenRouter",
          "GET /test/ai/claude - Test Claude via OpenRouter",
          "POST /process-video/:jobId - Process video in container",
        ]
      }, { headers: corsHeaders });
      
    } catch (error) {
      return Response.json({
        success: false,
        error: error instanceof Error ? error.message : "Unknown error"
      }, { status: 500, headers: corsHeaders });
    }
  },
  
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      console.log("Processing queue message:", message.body);
      message.ack();
    }
  }
};
