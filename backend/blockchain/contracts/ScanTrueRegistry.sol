// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

contract ScanTrueRegistry {
    address public immutable registrador;
    mapping(bytes16 => bool) public registrado;

    event AnalisisRegistrado(
        bytes16 indexed id,
        bytes32 hashTexto,
        uint64 fecha,
        bytes datos
    );

    error NoAutorizado();
    error YaRegistrado();

    constructor() {
        registrador = msg.sender;
    }

    function registrar(bytes16 id, bytes32 hashTexto, uint64 fecha, bytes calldata datos)
        external
    {
        if (msg.sender != registrador) revert NoAutorizado();
        if (registrado[id]) revert YaRegistrado();
        registrado[id] = true;
        emit AnalisisRegistrado(id, hashTexto, fecha, datos);
    }
}
