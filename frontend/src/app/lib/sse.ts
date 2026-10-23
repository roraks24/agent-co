export interface ParsedSseEvent {
  event: string;
  data: Record<string, unknown>;
}

export function parseSseBlock(block: string): ParsedSseEvent | null {
  const lines = block.split("\n").map((line) => line.replace(/\r$/, ""));
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim() || "message";
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  const rawData = dataLines.join("\n");
  try {
    return { event: eventName, data: JSON.parse(rawData) as Record<string, unknown> };
  } catch {
    return {
      event: "error",
      data: {
        message: "Failed to parse SSE payload.",
        raw: rawData
      }
    };
  }
}

export async function consumeSseStream(
  response: Response,
  onEvent: (event: ParsedSseEvent) => void
): Promise<void> {
  if (!response.ok) {
    throw new Error(`Stream request failed with status ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Stream response body is missing.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (parsed) {
        onEvent(parsed);
      }
    }
  }

  const tail = parseSseBlock(buffer.trim());
  if (tail) {
    onEvent(tail);
  }
}
