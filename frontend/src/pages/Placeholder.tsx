export function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <section>
      <h1 className="text-3xl">{title}</h1>
      <p className="mt-3 max-w-xl text-tinte-weich">{text}</p>
    </section>
  )
}
