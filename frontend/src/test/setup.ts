import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Nhiều test cùng chạy song song làm máy chậm: nới thời gian chờ của findBy/waitFor để không flaky.
configure({ asyncUtilTimeout: 3000 })

afterEach(() => {
  cleanup()
})
