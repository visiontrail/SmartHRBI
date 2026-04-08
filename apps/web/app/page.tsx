import { ChatWorkbench } from "../components/workbench/chat-workbench";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function HomePage() {
  return <ChatWorkbench apiBaseUrl={apiBaseUrl} />;
}
