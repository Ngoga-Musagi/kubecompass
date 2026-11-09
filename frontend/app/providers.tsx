"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Tooltip } from "radix-ui";
import * as React from "react";

import { ToastProvider } from "@/components/ui/toast";
import { ConferenceProvider } from "@/hooks/use-conference";
import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Tooltip.Provider>
        <ToastProvider>
          <ConferenceProvider>{children}</ConferenceProvider>
        </ToastProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
