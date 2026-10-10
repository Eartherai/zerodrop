import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createApi } from "./api/client";
import { App } from "./App";
import "./index.css";

const container = document.getElementById("root");
if (!container) throw new Error("missing #root element");
const root = createRoot(container);

createApi()
  .then((api) =>
    root.render(
      <StrictMode>
        <App api={api} />
      </StrictMode>,
    ),
  )
  .catch((err: unknown) => {
    container.textContent = `ZeroDrop UI failed to start: ${err instanceof Error ? err.message : String(err)}`;
  });
