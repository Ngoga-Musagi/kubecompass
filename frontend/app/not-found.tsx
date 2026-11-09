import { Compass } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <Compass className="size-10 text-needle" />
      <h1 className="mt-4 font-display text-[40px]">Off the map</h1>
      <p className="mt-2 text-[14px] text-ink-3">That page doesn&apos;t exist. Let&apos;s get your bearings again.</p>
      <Link href="/" className="mt-6 inline-flex h-9 items-center rounded-[10px] bg-ink px-4 text-[13px] font-medium text-bg">
        Back to Discover
      </Link>
    </div>
  );
}
