/** Tên hiển thị: claim `name` của ID token nếu có, không thì phần đầu của email. */
export function displayName(email: string | undefined, name: string | undefined): string | undefined {
  if (name) return name
  const local = email?.split('@')[0]?.split(/[._-]/)[0]
  return local ? local.charAt(0).toUpperCase() + local.slice(1) : undefined
}
