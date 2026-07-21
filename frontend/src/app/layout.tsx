"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import CommandPalette from "@/components/CommandPalette";
import "./globals.css";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1 },
        },
      })
  );

  return (
    <html lang="zh-CN">
      <body>
        <QueryClientProvider client={queryClient}>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 p-8 overflow-auto">
              {children}
            </main>
          </div>
          <CommandPalette />
        </QueryClientProvider>
      </body>
    </html>
  );
}
