# PlantUML 建模约定

## 通用要求

- 每个文件只有一个 `@startuml` 和一个 `@enduml`。
- 图中只放能帮助回答当前问题的信息；复杂项目按领域或场景拆图。
- 关系标签使用简短动词，例如 `calls`、`contains`、`implements`、`reads`。
- 推断关系用虚线并标注 `inferred`，例如 `A ..> B : inferred`。
- 无法从静态源码确认的运行时关系写在 `note` 中，不要伪造实线关系。

## 用例图

```plantuml
@startuml
left to right direction
actor "用户" as User
rectangle "系统边界" {
  usecase "完成业务目标" as Goal
  usecase "校验输入" as Validate
}
User --> Goal
Goal .> Validate : <<include>>
@enduml
```

## 类图

```plantuml
@startuml
class Service {
  +execute(request): Response
}
interface Repository {
  +find(id): Entity
}
Service ..> Repository : uses
@enduml
```

## 时序图

```plantuml
@startuml
actor User
boundary API
control Service
database DB
User -> API : request
API -> Service : execute()
Service -> DB : query()
DB --> Service : result
Service --> API : response
API --> User : response
@enduml
```

## 活动图

```plantuml
@startuml
start
:接收请求;
if (输入有效?) then (是)
  :执行业务操作;
else (否)
  :返回校验错误;
endif
stop
@enduml
```

## 状态图

```plantuml
@startuml
[*] --> Created
Created --> Processing : submit
Processing --> Completed : success
Processing --> Failed : error
Failed --> Processing : retry
Completed --> [*]
@enduml
```

## ER 图

```plantuml
@startuml
entity users {
  * id : BIGINT <<PK>>
  --
  name : VARCHAR
}
entity orders {
  * id : BIGINT <<PK>>
  --
  user_id : BIGINT <<FK>>
}
users ||--o{ orders : places
@enduml
```
