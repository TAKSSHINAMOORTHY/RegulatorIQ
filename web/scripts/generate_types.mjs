import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";
import { compile } from "json-schema-to-typescript";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, "../..");
const OUT_DIR = path.resolve(__dirname, "../lib/generated");

async function generate() {
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  // 1. OpenAPI types
  const openapiPath = path.join(ROOT_DIR, "docs/openapi.json");
  console.log(`Reading OpenAPI schema from: ${openapiPath}`);
  const openapiContent = JSON.parse(fs.readFileSync(openapiPath, "utf-8"));
  const ast = await openapiTS(openapiContent);
  const openapiTypes = astToString(ast);
  const openapiOut = path.join(OUT_DIR, "openapi.ts");
  fs.writeFileSync(openapiOut, openapiTypes);
  console.log(`Generated: ${openapiOut}`);

  // 2. Events schema types
  const eventsSchemaPath = path.join(ROOT_DIR, "agent/events.schema.json");
  console.log(`Reading Events schema from: ${eventsSchemaPath}`);
  const eventsContent = JSON.parse(fs.readFileSync(eventsSchemaPath, "utf-8"));
  const eventTypes = await compile(eventsContent, "AgentEvent", {
    bannerComment: "/* eslint-disable */\n/**\n * Auto-generated from agent/events.schema.json\n * DO NOT EDIT DIRECTLY.\n */",
  });
  const eventsOut = path.join(OUT_DIR, "events.ts");
  fs.writeFileSync(eventsOut, eventTypes);
  console.log(`Generated: ${eventsOut}`);

  console.log("TypeScript generation complete!");
}

generate().catch((err) => {
  console.error("Error generating types:", err);
  process.exit(1);
});
