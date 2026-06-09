import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "local.agenthub.mobile",
  appName: "AgentHub Mobile",
  webDir: "../frontend/dist-mobile",
  server: {
    androidScheme: "https"
  }
};

export default config;
