import type { ComponentProps } from "react";
import { ProjectSidebar } from "../../components/ProjectSidebar";

export function SaasProjectSidebar(props: ComponentProps<typeof ProjectSidebar>) {
  return <ProjectSidebar {...props} productEdition="saas" />;
}
