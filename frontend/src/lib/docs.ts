import { Marked, type Tokens } from "marked";
import gettingStarted from "../../../docs/GETTING-STARTED.md?raw";
import architecture from "../../../docs/ARCHITECTURE.md?raw";
import mandateFormat from "../../../docs/MANDATE-FORMAT.md?raw";
import integration from "../../../docs/INTEGRATION.md?raw";
import threatModel from "../../../docs/THREAT-MODEL.md?raw";
import genvmNotes from "../../../docs/GENVM-NOTES.md?raw";

// The docs are the repository's own markdown, imported at build time. There is
// one copy, so the site cannot drift from the project. The HTML rendered from
// it is inserted directly; that is safe only because the source is bundled from
// this repository, never fetched or user-supplied.

export const REPO_URL = "https://github.com/Ritapossible/Remit";

export interface Doc {
  slug: string;
  title: string;
  file: string;
  group: "Guides" | "Reference";
  source: string;
}

export const DOCS: Doc[] = [
  { slug: "getting-started", title: "Getting started", file: "GETTING-STARTED.md", group: "Guides", source: gettingStarted },
  { slug: "concepts", title: "Concepts", file: "ARCHITECTURE.md", group: "Guides", source: architecture },
  { slug: "integration", title: "Integration", file: "INTEGRATION.md", group: "Guides", source: integration },
  { slug: "mandate-format", title: "Mandate format", file: "MANDATE-FORMAT.md", group: "Reference", source: mandateFormat },
  { slug: "threat-model", title: "Threat model", file: "THREAT-MODEL.md", group: "Reference", source: threatModel },
  { slug: "genvm-notes", title: "Building on GenVM", file: "GENVM-NOTES.md", group: "Reference", source: genvmNotes },
];

const BY_FILE = new Map(DOCS.map((d) => [d.file, d.slug]));

const slugify = (text: string) =>
  text
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/&[a-z]+;/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");

/** Map a link written for GitHub onto the site. */
function rewrite(href: string): { url: string; external: boolean } {
  if (/^(https?:|mailto:)/.test(href)) return { url: href, external: true };
  if (href.startsWith("#")) return { url: href, external: false };
  const base = href.split("#")[0];
  const name = base.split("/").pop() ?? "";
  if (name === "PLAN.md") return { url: "#/roadmap", external: false };
  const slug = BY_FILE.get(name);
  if (slug) return { url: `#/docs/${slug}`, external: false };
  // Anything else is a file in the repository, relative to docs/.
  const parts = ["docs", ...base.split("/")].reduce<string[]>((acc, p) => {
    if (p === "..") acc.pop();
    else if (p && p !== ".") acc.push(p);
    return acc;
  }, []);
  return { url: `${REPO_URL}/blob/main/${parts.join("/")}`, external: true };
}

export interface Rendered {
  html: string;
  toc: { id: string; text: string }[];
}

export function renderDoc(source: string): Rendered {
  const toc: { id: string; text: string }[] = [];
  const md = new Marked({ gfm: true });
  md.use({
    renderer: {
      heading(this: { parser: { parseInline(t: Tokens.Generic[]): string } }, token: Tokens.Heading) {
        const inner = this.parser.parseInline(token.tokens);
        if (token.depth === 1) return `<h1>${inner}</h1>`;
        const id = slugify(inner);
        if (token.depth === 2) toc.push({ id, text: inner.replace(/<[^>]+>/g, "") });
        return `<h${token.depth} id="${id}">${inner}</h${token.depth}>`;
      },
      link(this: { parser: { parseInline(t: Tokens.Generic[]): string } }, token: Tokens.Link) {
        const { url, external } = rewrite(token.href);
        const inner = this.parser.parseInline(token.tokens);
        return external
          ? `<a href="${url}" target="_blank" rel="noreferrer">${inner}</a>`
          : `<a href="${url}">${inner}</a>`;
      },
    },
  });
  const html = md.parse(source) as string;
  return { html, toc };
}

export function inline(text: string): string {
  return new Marked({ gfm: true }).parseInline(text) as string;
}
