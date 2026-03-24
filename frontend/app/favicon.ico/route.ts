import { readFile } from "fs/promises";
import path from "path";

export async function GET() {
  const logoPath = path.join(process.cwd(), "public", "logo.png");
  const logo = await readFile(logoPath);

  return new Response(logo, {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=86400, immutable",
    },
  });
}
