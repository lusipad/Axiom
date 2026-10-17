import indexData from "./fixtures/index.json";

interface FixtureEntryFile {
  file: string;
  requestFile?: string;
}

type FixtureIndexFile = Record<string, FixtureEntryFile[]>;

const fixtureModules = import.meta.glob(["./fixtures/*.json", "!./fixtures/index.json"], { eager: true }) as Record<string, { default?: unknown } | undefined>;

function loadModule(file: string): unknown {
  const mod = fixtureModules[`./fixtures/${file}`];
  if (!mod) throw new Error(`demo fixture missing: ${file}`);
  return "default" in mod && mod.default !== undefined ? mod.default : mod;
}

const indexEntries = Object.entries(indexData as FixtureIndexFile);

export const demoFixtures: ReadonlyMap<string, ReadonlyArray<{ response: unknown; request: unknown | null }>> = new Map(
  indexEntries.map(([key, entries]) => [
    key,
    entries.map((entry) => ({
      response: loadModule(entry.file),
      request: entry.requestFile ? loadModule(entry.requestFile) : null,
    })),
  ]),
);
