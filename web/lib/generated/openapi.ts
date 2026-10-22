export interface paths {
    "/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ask Question
         * @description Execute regulatory analysis with streaming SSE or non-streaming JSON.
         */
        post: operations["ask_question_ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Submit Feedback
         * @description Submit rating and feedback for an /ask request.
         */
        post: operations["submit_feedback_feedback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Health
         * @description Return service liveness status and uptime.
         */
        get: operations["get_health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/meta": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Metadata
         * @description Return public engine metadata and corpus statistics with 60s cache header.
         */
        get: operations["get_metadata_meta_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/metrics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Metrics
         * @description Return Prometheus-formatted operational metrics.
         */
        get: operations["get_metrics_metrics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Ready
         * @description Return service readiness and loaded engine metadata.
         */
        get: operations["get_ready_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/version": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Version
         * @description Return version and commit identification.
         */
        get: operations["get_version_version_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/warmup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Execute Warmup
         * @description Pre-warm retrieval and reranking models without consuming LLM budget.
         */
        post: operations["execute_warmup_warmup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AskOptions
         * @description Execution options for regulatory search and generation.
         */
        AskOptions: {
            /**
             * As Of
             * @description Regulatory point-in-time date constraint (YYYY-MM-DD)
             */
            as_of?: string | null;
            /**
             * Doc Types
             * @description Filter documents by category/type
             */
            doc_types?: string[] | null;
            /**
             * Include Superseded
             * @description Whether to include superseded documents
             * @default false
             */
            include_superseded: boolean;
            /**
             * Interactive
             * @description Allow clarification request vs emit assumption
             * @default true
             */
            interactive: boolean;
        };
        /**
         * AskRequest
         * @description Input payload for POST /ask.
         */
        AskRequest: {
            /**
             * History
             * @description Recent conversation turns (max 4 round-trips)
             */
            history?: components["schemas"]["ConversationTurn"][];
            /** @description Search and generation options */
            options?: components["schemas"]["AskOptions"];
            /**
             * Question
             * @description Regulatory question
             */
            question: string;
        };
        /**
         * ConversationTurn
         * @description Single turn in previous conversation context.
         */
        ConversationTurn: {
            /**
             * Content
             * @description Turn content
             */
            content: string;
            /**
             * Role
             * @description Speaker role
             * @enum {string}
             */
            role: "user" | "assistant";
        };
        /**
         * FeedbackRequest
         * @description Input payload for POST /feedback.
         */
        FeedbackRequest: {
            /**
             * Comment
             * @description Optional user comment
             */
            comment?: string | null;
            /**
             * Rating
             * @description User rating
             * @enum {string}
             */
            rating: "up" | "down";
            /**
             * Reason
             * @description Category reason for rating
             */
            reason?: ("wrong_fact" | "outdated" | "missing_citation" | "unhelpful" | "other") | null;
            /**
             * Request Id
             * @description UUID of the /ask request being rated
             */
            request_id: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthResponse
         * @description Output payload for GET /health.
         */
        HealthResponse: {
            /**
             * Status
             * @default ok
             */
            status: string;
            /** Uptime S */
            uptime_s: number;
        };
        /**
         * MetaCorpus
         * @description Corpus summary stats for GET /meta.
         */
        MetaCorpus: {
            /** As Of Crawl Date */
            as_of_crawl_date: string;
            /** Chunks */
            chunks: number;
            /** Doc Types */
            doc_types: {
                [key: string]: number;
            };
            /** Documents */
            documents: number;
        };
        /**
         * MetaLimits
         * @description Request quotas and bounds for GET /meta.
         */
        MetaLimits: {
            /** Max History Turns */
            max_history_turns: number;
            /** Max Question Chars */
            max_question_chars: number;
        };
        /**
         * MetaResponse
         * @description Output payload for GET /meta.
         */
        MetaResponse: {
            /**
             * App
             * @default RegulatorIQ
             */
            app: string;
            /** Capabilities */
            capabilities: string[];
            corpus: components["schemas"]["MetaCorpus"];
            /** Degraded Notice */
            degraded_notice?: string | null;
            /** Disclaimer */
            disclaimer: string;
            /**
             * Disclaimer Key
             * @default regulatory_disclaimer
             */
            disclaimer_key: string;
            /** Index Version */
            index_version: string;
            limits: components["schemas"]["MetaLimits"];
            /** Mode */
            mode: string;
            /** Version */
            version: string;
        };
        /**
         * ReadyResponse
         * @description Output payload for GET /ready.
         */
        ReadyResponse: {
            /** Chunk Count */
            chunk_count: number;
            /** Degraded */
            degraded: string[];
            /** Elapsed S */
            elapsed_s?: number | null;
            /** Hint */
            hint?: string | null;
            /** Index Version */
            index_version: string;
            /** Mode */
            mode: string;
            /** Stage */
            stage?: string | null;
            /** Started At */
            started_at: string;
            /** Status */
            status: string;
            /** Version */
            version: string;
            /** Warmup Enabled */
            warmup_enabled: boolean;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * VersionResponse
         * @description Output payload for GET /version.
         */
        VersionResponse: {
            /** Build Time */
            build_time: string;
            /** Git Sha */
            git_sha: string;
            /** Index Version */
            index_version: string;
            /** Mode */
            mode: string;
            /** Version */
            version: string;
        };
        /**
         * WarmupResponse
         * @description Output payload for POST /warmup.
         */
        WarmupResponse: {
            /**
             * Llm Called
             * @default false
             */
            llm_called: boolean;
            /** Mode */
            mode: string;
            /**
             * Ok
             * @default true
             */
            ok: boolean;
            /** Timings Ms */
            timings_ms: {
                [key: string]: number;
            };
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    ask_question_ask_post: {
        parameters: {
            query?: never;
            header?: {
                accept?: string | null;
                "X-API-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_feedback_feedback_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeedbackRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    get_metadata_meta_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetaResponse"];
                };
            };
        };
    };
    get_metrics_metrics_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ready_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadyResponse"];
                };
            };
        };
    };
    get_version_version_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
        };
    };
    execute_warmup_warmup_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WarmupResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
