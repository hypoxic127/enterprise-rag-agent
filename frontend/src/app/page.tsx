import { ChatContainer } from "@/components/chat/ChatContainer";

export default function Home() {
  return (
    <div className="relative h-dvh w-full overflow-clip bg-gradient-to-br from-zinc-950 via-zinc-900 to-black">
      {/* Abstract Background Orbs */}
      <div className="pointer-events-none absolute left-[-10%] top-[-10%] h-[500px] w-[500px] rounded-full bg-blue-600/20 blur-[120px]" />
      <div className="pointer-events-none absolute bottom-[-10%] right-[-10%] h-[500px] w-[500px] rounded-full bg-purple-600/20 blur-[120px]" />

      {/* Full-height Chat Interface */}
      <div className="relative flex h-full w-full">
        <ChatContainer />
      </div>
    </div>
  );
}
