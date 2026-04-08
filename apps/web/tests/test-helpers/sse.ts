type StreamChunk = {
  id: number;
  event: string;
  data: unknown;
};

export function createSSEEventStream(chunks: StreamChunk[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(
          encoder.encode(
            `id: ${chunk.id}\nevent: ${chunk.event}\ndata: ${JSON.stringify(chunk.data)}\n\n`
          )
        );
      }
      controller.close();
    }
  });
}
