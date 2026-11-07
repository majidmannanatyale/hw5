import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the dashboard on :5175. It calls the FastAPI backend
// directly at http://localhost:8000 (the backend allows this origin via CORS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5175 },
});
