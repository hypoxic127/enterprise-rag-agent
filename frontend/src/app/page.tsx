import { ChatContainer } from "@/components/chat/ChatContainer";

export default function Home() {
  return (
    <main className="flex h-screen flex-col bg-gradient-to-br from-zinc-950 via-zinc-900 to-black relative overflow-hidden">
      {/* Abstract Background Orbs */}
      <div className="absolute top-[-10%] left-[-10%] h-[500px] w-[500px] rounded-full bg-blue-600/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] h-[500px] w-[500px] rounded-full bg-purple-600/20 blur-[120px] pointer-events-none" />
      
      {/* Header */}
      <header className="relative w-full p-4 text-center z-10 border-b border-white/5 bg-background/50 backdrop-blur-md">
        <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
          Enterprise RAG Agent
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5 tracking-widest uppercase">
          Powered by Gemini 2.5 Pro &amp; Next.js
        </p>
      </header>

      {/* Main Chat Interface (fills remaining height) */}
      <div className="z-10 flex flex-1 overflow-hidden">
        <ChatContainer />
      </div>
    </main>
  );
}
