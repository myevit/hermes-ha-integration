// Fork-owned visual harness (test-only): mounts the UNMODIFIED Desktop components
// (UserMessage / SystemMessage / AssistantMessage) through the same primitive the
// real thread uses (ThreadPrimitive.MessageByIndex), inside the same row wrappers
// the real ThreadMessageList builds (see thread/list.tsx TurnRow), driven by the
// actual REST/gateway history rows after the real hydration + runtime-message
// conversion. It adds no product UI; it only gives the real components a real
// browser with the real theme and stylesheet to paint in.
import { AssistantRuntimeProvider, ThreadPrimitive, useExternalStoreRuntime, type ThreadMessage } from '@assistant-ui/react'
import { createRoot } from 'react-dom/client'

import { AssistantMessage } from '@/components/assistant-ui/thread/assistant-message'
import { SystemMessage } from '@/components/assistant-ui/thread/system-message'
import { UserMessage } from '@/components/assistant-ui/thread/user-message'
import { toChatMessages } from '@/lib/chat-messages'
import { toRuntimeMessage } from '@/lib/chat-runtime'
// Side-effect import: the app's own boot paint applies the resolved skin/mode to
// documentElement, so the harness inherits the real theme instead of a guess.
import '@/themes/context'

const rows = (window as unknown as { __ROWS__: unknown[] }).__ROWS__
const messages: ThreadMessage[] = toChatMessages(rows).map(toRuntimeMessage)
const components = {
  AssistantMessage: () => <AssistantMessage />,
  SystemMessage,
  UserMessage: () => <UserMessage />
}

function Harness() {
  const runtime = useExternalStoreRuntime<ThreadMessage>({ messages, isRunning: false, onNew: async () => {} })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root>
        <ThreadPrimitive.Viewport>
          {messages.map((message, index) => (
            // Same wrappers the real transcript row uses, so alignment, gap and
            // the sticky user bubble see the layout they see in the app.
            <div
              className="flex min-w-0 flex-col gap-(--conversation-turn-gap) pb-(--conversation-turn-gap) [contain-intrinsic-size:auto_37.5rem]"
              data-slot="aui_message-group"
              key={message.id}
            >
              <div
                className="composer-human-ai-pair-container relative flex min-w-0 flex-col gap-(--conversation-turn-gap)"
                data-slot="aui_turn-pair"
              >
                <ThreadPrimitive.MessageByIndex components={components} index={index} />
              </div>
            </div>
          ))}
        </ThreadPrimitive.Viewport>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Harness />)
;(window as unknown as { __MOUNTED__: boolean }).__MOUNTED__ = true
