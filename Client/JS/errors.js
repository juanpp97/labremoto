class PermissionError extends Error {
    constructor(message) {
        super(message);
        this.name = 'PermissionError';
    }
}
class StatusError extends Error {
    constructor(message) {
        super(message);
        this.name = 'StatusError';
    }
}
class GraphError extends Error {
    constructor(message) {
        super(message);
        this.name = 'GraphError';
    }
}

export { PermissionError, StatusError, GraphError };
