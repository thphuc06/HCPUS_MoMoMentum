// Đo kích thước gzip theo nhóm gói (có minify): npx vite build -c vite.analyze.config.ts
// Ghi ra dist-analyze/ (không đụng dist/). Tách nhóm chỉ để đo; app thật nên tự quyết chia chunk.
import base from './vite.config'
import { mergeConfig } from 'vite'

const nm = (names: string) => new RegExp(`node_modules/(${names})/`)
export default mergeConfig(base, {
  build: {
    outDir: 'dist-analyze',
    chunkSizeWarningLimit: 5000,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'g-recharts', test: nm('recharts|d3-[a-z-]+|victory-vendor|es-toolkit|@reduxjs/toolkit|redux|immer|reselect|decimal.js-light|internmap|use-sync-external-store|react-redux|eventemitter3'), priority: 50 },
            { name: 'g-agui', test: nm('@ag-ui/[a-z]+|rxjs|fast-json-patch|@bufbuild/protobuf|untruncate-json|uuid|compare-versions|@types/uuid'), priority: 50 },
            { name: 'g-zod', test: nm('zod'), priority: 70 },
            { name: 'g-motion', test: nm('motion|motion-dom|motion-utils|framer-motion'), priority: 50 },
            { name: 'g-numberflow', test: nm('@number-flow/react|number-flow'), priority: 50 },
            { name: 'g-react', test: nm('react|react-dom|scheduler|react-is'), priority: 40 },
            { name: 'g-baseui', test: nm('@base-ui/react|@base-ui/utils|@floating-ui/[a-z-]+|@shadcn/react|tabbable'), priority: 50 },
            { name: 'g-cn-lucide-misc', test: nm('cn|lucide-react|class-variance-authority|clsx|tailwind-merge'), priority: 50 },
          ],
        },
      },
    },
  },
})
