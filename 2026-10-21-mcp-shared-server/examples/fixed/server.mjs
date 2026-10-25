// The shape the README shows from 2 Oct 2026: a new server and transport per request.
import { createServer } from 'node:http';
import { NodeStreamableHTTPServerTransport } from '@modelcontextprotocol/node';
import { McpServer } from '@modelcontextprotocol/server';

createServer(async (req, res) => {
    // Stateless example: create a server and a transport per request.
    const server = new McpServer({ name: 'my-server', version: '1.0.0' });
    const transport = new NodeStreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    await server.connect(transport);
    await transport.handleRequest(req, res);
}).listen(3000, '127.0.0.1');
