import Chat from '@/components/Chat'

export default function Home() {
  return (
    <main className="flex h-screen w-screen flex-col bg-stone-900 text-stone-100 font-sans pb-10">
      <header className="flex h-16 items-center border-b border-stone-800 bg-stone-950 px-6 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-orange-600 font-bold text-white shadow-sm">
            H
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-white">Houdini AI Assistant</h1>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden p-6 mx-auto w-full max-w-4xl gap-6">
        {/* Main Chat Area */}
        <section className="flex flex-col flex-1 rounded-xl border border-stone-800 bg-stone-950/50 shadow-2xl relative overflow-hidden backdrop-blur-xl">
          <Chat />
        </section>
      </div>
    </main>
  )
}
