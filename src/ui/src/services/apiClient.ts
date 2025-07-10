// Mock API client for now
// In a real app, this would handle actual HTTP requests, base URL, auth tokens, etc.

const API_BASE_URL = "/api"; // Example base URL, assuming UI is served on same domain or proxied

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
  body?: any; // Will be stringified if object
}

// Mocks a delay and returns a predefined response or error
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function mockRequest<T>(path: string, options?: RequestOptions, mockResponse?: T, succeed: boolean = true, delay: number = 300): Promise<T> {
  console.log(`Mock API Request: ${options?.method || 'GET'} ${API_BASE_URL}${path}`, options?.body);

  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (succeed) {
        if (mockResponse !== undefined) {
          resolve(mockResponse);
        } else {
          // For methods like DELETE or if no specific response body is needed for success
          resolve(undefined as unknown as T);
        }
      } else {
        reject(new Error(`Mock API Error: Failed to ${options?.method || 'GET'} ${path}`));
      }
    }, delay);
  });
}

export const apiClient = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async get<T>(path: string, mockResponse?: T, succeed: boolean = true): Promise<T> {
    return mockRequest<T>(path, { method: 'GET' }, mockResponse, succeed);
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async post<T_Res, T_Req = any>(path: string, data: T_Req, mockResponse?: T_Res, succeed: boolean = true): Promise<T_Res> {
    return mockRequest<T_Res>(path, { method: 'POST', body: data, headers: {'Content-Type': 'application/json'} }, mockResponse, succeed);
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async put<T_Res, T_Req = any>(path: string, data: T_Req, mockResponse?: T_Res, succeed: boolean = true): Promise<T_Res> {
    return mockRequest<T_Res>(path, { method: 'PUT', body: data, headers: {'Content-Type': 'application/json'} }, mockResponse, succeed);
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async patch<T_Res, T_Req = any>(path: string, data: T_Req, mockResponse?: T_Res, succeed: boolean = true): Promise<T_Res> {
    return mockRequest<T_Res>(path, { method: 'PATCH', body: data, headers: {'Content-Type': 'application/json'} }, mockResponse, succeed);
  },
  async delete<T_Res>(path: string, mockResponse?: T_Res, succeed: boolean = true): Promise<T_Res> {
    return mockRequest<T_Res>(path, { method: 'DELETE' }, mockResponse, succeed);
  },
};

// Example of how it might look with actual fetch:
/*
async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options?.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      // Authorization: `Bearer ${getToken()}`, // Example auth
      ...options?.headers,
    },
    body: options?.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(errorData.message || `API request failed with status ${response.status}`);
  }
  if (response.status === 204) { // No Content
    return undefined as unknown as T;
  }
  return response.json();
}
*/
