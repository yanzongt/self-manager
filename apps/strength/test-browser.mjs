import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const result = spawnSync(
  process.execPath,
  [fileURLToPath(new URL("../../tests/test_strength.js", import.meta.url))],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      PLAYWRIGHT_CORE: fileURLToPath(
        new URL(".generated/node_modules/playwright-core", import.meta.url),
      ),
    },
  },
);
process.exit(result.status ?? 1);
