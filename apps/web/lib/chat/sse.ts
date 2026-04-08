export type SSEEvent = {
  id?: string;
  event: string;
  data: unknown;
};

export async function* parseSSEStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<SSEEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const event = parseSSEFrame(frame);
      if (event) {
        yield event;
      }
    }
  }

  if (buffer.trim()) {
    const event = parseSSEFrame(buffer);
    if (event) {
      yield event;
    }
  }
}

function parseSSEFrame(frame: string): SSEEvent | null {
  const lines = frame.split("\n");
  let id: string | undefined;
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  const mergedData = dataLines.join("\n");
  try {
    return {
      id,
      event,
      data: JSON.parse(mergedData)
    };
  } catch {
    return {
      id,
      event,
      data: mergedData
    };
  }
}
