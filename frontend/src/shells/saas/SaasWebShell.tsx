import { AgentHubWorkbench } from "../../App";
import { AuthGate } from "./AuthGate";

export function SaasWebShell() {
  return (
    <AuthGate surface="desktop">
      <AgentHubWorkbench />
    </AuthGate>
  );
}
