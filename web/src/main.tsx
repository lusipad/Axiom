import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { installDemoFetch } from "./demo/installDemoFetch";
import "./styles.css";

void installDemoFetch().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
