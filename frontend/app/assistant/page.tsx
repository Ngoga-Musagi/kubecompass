import { redirect } from "next/navigation";

// The assistant grew into the attendee's event agent (it still answers open questions).
export default function AssistantPage() {
  redirect("/agent");
}
