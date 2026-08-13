import { defineConfig } from "orval"

const input = {
  target: "../api/openapi.yaml",
}

export default defineConfig({
  dashboard: {
    input,
    output: {
      target: "./src/api/generated/client/index.ts",
      schemas: "./src/api/generated/models",
      client: "react-query",
      httpClient: "fetch",
      mode: "split",
      clean: true,
      indexFiles: true,
      baseUrl: {
        runtime: "API_RUNTIME_BASE_URL",
        imports: [{ name: "API_RUNTIME_BASE_URL", importPath: "../../runtime" }],
      },
      mock: {
        path: "./src/api/generated/mocks",
        generators: [{ type: "msw", operationResponses: false }],
      },
      override: {
        requestOptions: {
          credentials: "same-origin",
        },
      },
    },
  },
  schemas: {
    input,
    output: {
      target: "./src/api/generated/schemas/index.ts",
      client: "zod",
      mode: "single",
      clean: true,
      override: {
        zod: {
          version: 4,
        },
      },
    },
  },
})
