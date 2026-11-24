import { useState } from 'react'
import { HStack, VStack, Layout, LayoutContent } from '@astryxdesign/core/Layout'
import { Heading, Text } from '@astryxdesign/core/Text'
import {
  ChatComposer,
  ChatLayout,
  ChatMessage,
  ChatMessageBubble,
  ChatMessageList,
  ChatMessageMetadata,
  ChatSystemMessage,
  ChatToolCalls,
} from '@astryxdesign/core/Chat'
import { Avatar } from '@astryxdesign/core/Avatar'
import { Button } from '@astryxdesign/core/Button'
import { Markdown } from '@astryxdesign/core/Markdown'
import { Token } from '@astryxdesign/core/Token'
import { api, type ChatReply } from '../api'

type Turn = { id: number; who: 'user' | 'hive'; text: string; reply?: ChatReply; failed?: boolean }

const SUGGESTIONS = [
  "What's my last PR?",
  'What did I do last push workout?',
  "What's my best bench?",
  'How is my squat progressing?',
  'Why did my lifts drop?',
  'How did I sleep this week?',
  'Am I cutting?',
  'Which lifts improved the most?',
]

const TIER = ['code, no model', 'small local model', 'local model (gemma)']

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')

  const send = async (text: string) => {
    const q = text.trim()
    if (!q || busy) return
    setDraft('')
    const id = Date.now()
    setTurns(t => [...t, { id, who: 'user', text: q }])
    setBusy(true)
    try {
      const reply = await api.chat(q)
      setTurns(t => [...t, { id: id + 1, who: 'hive', text: reply.reply, reply }])
    } catch (e) {
      setTurns(t => [...t, { id: id + 1, who: 'hive', text: `The hive didn't answer (${String(e)}). Is the stack up?`, failed: true }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Layout
      height="fill"
      content={
        <LayoutContent role="main" padding={0}>
          <VStack height="100%">
          <ChatLayout
            density="balanced"
            style={{ flex: 1, minHeight: 0 }}
            emptyState={
              <VStack gap={4} hAlign="center">
                <Heading level={2}>Ask your hive</Heading>
                <Text color="secondary">
                  Common questions are answered by code from your own data. Anything else goes to a small local model
                  that can only use numbers the agents looked up.
                </Text>
                <HStack gap={2} wrap="wrap" hAlign="center">
                  {SUGGESTIONS.map(s => (
                    <Button key={s} label={s} variant="secondary" size="sm" onClick={() => send(s)} />
                  ))}
                </HStack>
              </VStack>
            }
            composer={
              <ChatComposer
                value={draft}
                onChange={setDraft}
                onSubmit={send}
                isDisabled={busy}
                placeholder="Ask about your training, sleep or food, or paste a workout log..."
              />
            }>
            {turns.length > 0 ? (
            <ChatMessageList isStreaming={busy}>
              <ChatSystemMessage variant="divider">This session</ChatSystemMessage>
              {turns.map(t =>
                t.who === 'user' ? (
                  <ChatMessage key={t.id} sender="user">
                    <ChatMessageBubble>{t.text}</ChatMessageBubble>
                  </ChatMessage>
                ) : (
                  <ChatMessage key={t.id} sender="assistant" avatar={<Avatar name="Daemon hive" size="md" />}>
                    {t.reply && t.reply.steps.length > 0 && (
                      <ChatToolCalls
                        calls={t.reply.steps.map((s, i) => ({
                          key: String(i),
                          name: s.tool,
                          target: JSON.stringify(s.args),
                          status: 'complete' as const,
                        }))}
                      />
                    )}
                    <ChatMessageBubble variant="ghost">
                      <Markdown density="compact">{t.text}</Markdown>
                    </ChatMessageBubble>
                    {t.reply && (
                      <ChatMessageMetadata
                        footer={
                          <HStack gap={1} wrap="wrap">
                            <Token size="sm" label={t.reply.route} color="blue" />
                            <Token
                              size="sm"
                              label={`tier ${t.reply.tier}: ${TIER[t.reply.tier] ?? ''}`}
                              color={t.reply.tier === 0 ? 'green' : 'purple'}
                            />
                          </HStack>
                        }
                      />
                    )}
                  </ChatMessage>
                ),
              )}
              {busy && <ChatSystemMessage>Asking the agents...</ChatSystemMessage>}
            </ChatMessageList>
            ) : null}
          </ChatLayout>
          </VStack>
        </LayoutContent>
      }
    />
  )
}
