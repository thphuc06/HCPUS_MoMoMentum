import { BlockSchema, blockSchemas } from '../src/blocks/schemas.ts'
import { sampleBlocks } from '../src/blocks/fixtures.ts'

for (const b of sampleBlocks() as { type: string; id: string }[]) {
  const viaUnion = BlockSchema.safeParse(b)
  const s = (blockSchemas as Record<string, { safeParse: (x: unknown) => { success: boolean } }>)[b.type]
  const viaRegistry = s ? s.safeParse(b).success : 'no-schema'
  console.log(b.type.padEnd(20), b.id.padEnd(16), 'union:', viaUnion.success, 'registry:', viaRegistry)
}
