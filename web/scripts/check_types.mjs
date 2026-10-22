import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";
import { compile } from "json-schema-to-typescript";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, "../..");
const OUT_DIR = path.resolve(__dirname, "../lib/generated");

async function check() {
  const openapiPath = path.join(ROOT_DIR, "docs/openapi.json");
  const openapiContent = JSON.parse(fs.readFileSync(openapiPath, "utf-8"));
  const ast = await openapiTS(openapiContent);
  const freshOpenapi = astToString(ast);

  const openapiOut = path.join(OUT_DIR, "openapi.ts");
  if (!fs.existsSync(openapiOut)) {
    console.error(`Missing generated file: ${openapiOut}`);
    process.exit(1);
  }
  const currentOpenapi = fs.readFileSync(openapiOut, "utf-8");
  if (currentOpenapi.trim() !== freshOpenapi.trim()) {
    console.error("OpenAPI generated types are out of date! Run `make web-types`.");
    process.exit(1);
  }

  const eventsSchemaPath = path.join(ROOT_DIR, "agent/events.schema.json");
  const eventsContent = JSON.parse(fs.readFileSync(eventsSchemaPath, "utf-8"));
  const freshEvents = await compile(eventsContent, "AgentEvent", {
    bannerComment: "/* eslint-disable */\n/**\n * Auto-generated from agent/events.schema.json\n * DO NOT EDIT DIRECTLY.\n */",
  });

  const eventsOut = path.join(OUT_DIR, "events.ts");
  if (!fs.existsSync(eventsOut)) {
    console.error(`Missing generated file: ${eventsOut}`);
    process.exit(1);
  }
  const currentEvents = fs.readFileSync(eventsOut, "utf-8");
  if (currentEvents.trim() !== freshEvents.trim()) {
    console.error("Events schema generated types are out of date! Run `make web-types`.");
    process.exit(1);
  }

  console.log("All generated types in web/lib/generated/ are up-to-date.");
}

check().catch((err) => {
  console.error("Type check error:", err);
  process.exit(1);
});
